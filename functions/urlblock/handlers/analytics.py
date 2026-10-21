"""Handler that builds domain-blocking analytics from firewall events."""

# Handlers deliberately catch every exception to log it and return a 500 response.
# pylint: disable=broad-exception-caught

import traceback
from datetime import datetime, timedelta
from collections import defaultdict
from logging import Logger

import pytz
from crowdstrike.foundry.function import Request, Response
from falconpy import FirewallManagement

from app_core import FUNC, get_client
from app_utils import query_param, _validate_falcon_response

DEFAULT_DAYS = 15  # look-back window when the request does not set ?days=
MAX_DAYS = 90

@FUNC.handler(method='GET', path='/domain-analytics')
# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def get_domain_analytics(request: Request, _: dict, logger: Logger) -> Response:
    """Generate analytics for domain blocking events of the last `days` days (?days=, default 15)."""
    logger.info("Starting /domain-analytics handler")
    days_param = query_param(request, 'days', str(DEFAULT_DAYS)).strip()
    if not days_param.isdigit() or not 1 <= int(days_param) <= MAX_DAYS:
        return Response(code=400, body={"error": f"days must be a whole number between 1 and {MAX_DAYS}"})
    days = int(days_param)

    try:  # pylint: disable=too-many-nested-blocks
        try:
            firewall_mgmt = get_client(FirewallManagement)
        except Exception as e:
            logger.error(f"Failed to initialize Falcon client: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(code=500, body={"error": "Falcon client initialization failed"})

        # Fetch events for the requested window
        end_time = datetime.now(pytz.UTC)
        start_time = end_time - timedelta(days=days)
        time_filter = f"timestamp:>'{start_time.isoformat()}'"

        logger.info(f"Fetching events from {start_time} to {end_time}")

        domain_visits: dict = defaultdict(int)
        domain_ips: dict = defaultdict(set)
        domain_hosts: dict = defaultdict(set)
        domain_first_seen: dict = {}
        domain_last_seen: dict = {}
        domain_policy: dict = {}
        domain_rule: dict = {}
        daily_blocks: dict = defaultdict(int)
        all_unique_hosts: set = set()

        offset = 0
        limit = 500
        max_pages = 20  # cap: 10,000 events per request
        pages = 0
        pages_read = 0  # pages whose events were actually read
        truncated = False
        error = None

        while True:
            if pages >= max_pages:
                truncated = True
                break
            pages += 1
            try:
                query_response = firewall_mgmt.query_events(parameters={
                    'filter': time_filter,
                    'limit': limit,
                    'offset': offset,
                    'sort': 'timestamp.desc'
                })

                if query_response['status_code'] != 200:
                    _ok, error = _validate_falcon_response(query_response, "query_events", logger)
                    truncated = True
                    break
                if not query_response['body']['resources']:
                    pages_read += 1
                    break

                event_ids = query_response['body']['resources']
                events_response = firewall_mgmt.get_events(ids=event_ids)

                if events_response['status_code'] != 200:
                    _ok, error = _validate_falcon_response(events_response, "get_events", logger)
                    truncated = True
                else:
                    pages_read += 1
                    for event in events_response['body']['resources']:
                        if 'domain_name_list' not in event:
                            continue

                        domain = event['domain_name_list']
                        remote_ip = event.get('remote_address', '')
                        host = event.get('host_name', 'Unknown')
                        policy = event.get('policy_name', 'Unknown')
                        rule = event.get('rule_name', 'Unknown')

                        try:
                            ts = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                        except (KeyError, ValueError):
                            ts = None

                        domain_visits[domain] += 1
                        domain_ips[domain].add(remote_ip)
                        domain_hosts[domain].add(host)
                        all_unique_hosts.add(host)

                        if ts is not None:
                            if domain not in domain_first_seen:
                                domain_first_seen[domain] = ts
                                domain_last_seen[domain] = ts
                            else:
                                if ts < domain_first_seen[domain]:
                                    domain_first_seen[domain] = ts
                                if ts > domain_last_seen[domain]:
                                    domain_last_seen[domain] = ts
                            daily_blocks[ts.date().isoformat()] += 1

                        if domain not in domain_policy:
                            domain_policy[domain] = policy
                            domain_rule[domain] = rule

                offset += limit
                if len(event_ids) < limit:
                    break

            except Exception as e:
                logger.error(f"Error fetching events batch: {str(e)}")
                error = "Unexpected error while reading firewall events"
                truncated = True
                break

        # Nothing could be read at all: an empty report would read as "nothing was blocked"
        if pages_read == 0 and error:
            return Response(code=502, body={"error": f"Failed to read firewall events from Falcon: {error}"})

        logger.info(f"Total unique domains aggregated: {len(domain_visits)}")

        top_domains = sorted(domain_visits.items(), key=lambda x: x[1], reverse=True)[:20]
        total_blocks = sum(domain_visits.values())

        domain_analysis = {}
        for domain, count in top_domains:
            domain_analysis[domain] = {
                'visit_count': count,
                'unique_ips': len(domain_ips[domain]),
                'unique_hosts': len(domain_hosts[domain]),
                'first_seen': domain_first_seen[domain].isoformat() if domain in domain_first_seen else None,
                'last_seen': domain_last_seen[domain].isoformat() if domain in domain_last_seen else None,
                'policy_name': domain_policy.get(domain, 'Unknown'),
                'rule_name': domain_rule.get(domain, 'Unknown')
            }

        visualization_data = {
            'bar_chart': {
                'domains': [d for d, _ in top_domains],
                'visits': [c for _, c in top_domains]
            },
            'comparison_chart': {
                'domains': [d for d, _ in top_domains[:10]],
                'visits': [c for _, c in top_domains[:10]],
                'unique_ips': [len(domain_ips[d]) for d, _ in top_domains[:10]]
            },
            'summary': {
                'total_blocks': total_blocks,
                'unique_domains': len(domain_analysis),
                'unique_hosts': len(all_unique_hosts)
            }
        }

        return Response(
            code=200,
            body={
                'days': days,
                'analysis': domain_analysis,
                'visualization_data': visualization_data,
                'truncated': truncated,
                'message': "Results may be incomplete" if truncated else None
            }
        )

    except Exception as e:
        logger.error(f"Error in domain analytics: {str(e)}")
        logger.error(traceback.format_exc())
        return Response(code=500, body={"error": "Failed to generate analytics"})
