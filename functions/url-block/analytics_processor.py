"""Analytics processing utilities for URL filtering."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import pytz
from crowdstrike.foundry.function import cloud
from falconpy import APIHarnessV2, FirewallManagement

from exceptions import AnalyticsError, FirewallAPIError


def initialize_firewall_management():
    """Initialize firewall management client."""
    try:
        falcon = APIHarnessV2(debug=True)
        firewall_mgmt = FirewallManagement(falcon, base_url=cloud())
        return firewall_mgmt
    except Exception as e:
        raise FirewallAPIError(f"Failed to initialize firewall management: {str(e)}") from e


def _process_events_batch(firewall_mgmt, time_filter, limit, offset):
    """Process a single batch of firewall events."""
    query_response = firewall_mgmt.query_events(parameters={
        'filter': time_filter,
        'limit': limit,
        'offset': offset,
        'sort': 'timestamp.desc'
    })

    if query_response['status_code'] != 200 or not query_response['body']['resources']:
        return [], True  # Empty events, should break

    event_ids = query_response['body']['resources']
    events_response = firewall_mgmt.get_events(ids=event_ids)

    batch_events = []
    if events_response['status_code'] == 200:
        events = events_response['body']['resources']
        for event in events:
            if 'domain_name_list' in event:
                batch_events.append({
                    'domain': event['domain_name_list'],
                    'timestamp': event['timestamp'],
                    'remote_address': event['remote_address'],
                    'host_name': event.get('host_name', 'Unknown'),
                    'policy_name': event.get('policy_name', 'Unknown'),
                    'rule_name': event.get('rule_name', 'Unknown')
                })

    should_break = len(event_ids) < limit
    return batch_events, should_break


def fetch_firewall_events(days_back=15, limit=500):
    """Fetch firewall events from the last N days."""
    try:
        firewall_mgmt = initialize_firewall_management()

        # Calculate time range
        end_time = datetime.now(pytz.UTC)
        start_time = end_time - timedelta(days=days_back)
        time_filter = f"timestamp:>'{start_time.isoformat()}'"

        all_events = []
        offset = 0

        while True:
            try:
                batch_events, should_break = _process_events_batch(
                    firewall_mgmt, time_filter, limit, offset
                )
                all_events.extend(batch_events)

                if should_break:
                    break

                offset += limit

            except Exception as e:
                raise AnalyticsError(f"Error fetching events batch: {str(e)}") from e

        return all_events

    except (AnalyticsError, FirewallAPIError):
        raise
    except Exception as e:
        raise AnalyticsError(f"Failed to fetch firewall events: {str(e)}") from e


def _calculate_domain_stats(domain_events):
    """Calculate statistics for a specific domain's events."""
    unique_ips = len(set(e['remote_address'] for e in domain_events))
    domain_hosts = len(set(e['host_name'] for e in domain_events))

    # Get timestamps for first and last blocks
    timestamps = [datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))
                 for e in domain_events]

    return {
        'unique_ips': unique_ips,
        'unique_hosts': domain_hosts,
        'timestamps': timestamps,
        'first_seen': min(timestamps).isoformat(),
        'last_seen': max(timestamps).isoformat(),
        'policy_name': domain_events[0].get('policy_name', 'Unknown'),
        'rule_name': domain_events[0].get('rule_name', 'Unknown')
    }


def analyze_domain_events(events):
    """Analyze domain events and return structured data."""
    try:
        # Count domain occurrences
        domain_counter = Counter(event['domain'] for event in events)
        top_domains = domain_counter.most_common(20)  # Get top 20 domains

        # Initialize analysis data
        domain_analysis = {}
        daily_blocks = defaultdict(int)
        total_blocks = 0
        unique_hosts = set()

        # Analyze each domain
        for domain, count in top_domains:
            domain_events = [e for e in events if e['domain'] == domain]
            stats = _calculate_domain_stats(domain_events)

            domain_analysis[domain] = {
                'visit_count': count,
                'unique_ips': stats['unique_ips'],
                'unique_hosts': stats['unique_hosts'],
                'first_seen': stats['first_seen'],
                'last_seen': stats['last_seen'],
                'policy_name': stats['policy_name'],
                'rule_name': stats['rule_name']
            }

            # Update totals
            total_blocks += count
            unique_hosts.update(e['host_name'] for e in domain_events)

            # Group by date for timeline
            for timestamp in stats['timestamps']:
                date_str = timestamp.date().isoformat()
                daily_blocks[date_str] += 1

        return {
            'domain_analysis': domain_analysis,
            'top_domains': top_domains,
            'daily_blocks': daily_blocks,
            'total_blocks': total_blocks,
            'unique_hosts': unique_hosts
        }

    except Exception as e:
        raise AnalyticsError(f"Failed to analyze domain events: {str(e)}") from e


def prepare_visualization_data(analysis_data):
    """Prepare data for visualization components."""
    try:
        top_domains = analysis_data['top_domains']
        domain_analysis = analysis_data['domain_analysis']

        # Prepare visualization data to match what the React component expects
        visualization_data = {
            'bar_chart': {
                'domains': [domain for domain, _ in top_domains],
                'visits': [count for _, count in top_domains]
            },
            'comparison_chart': {
                'domains': [domain for domain, _ in top_domains[:10]],
                'visits': [count for _, count in top_domains[:10]],
                'unique_ips': [domain_analysis[domain]['unique_ips'] for domain, _ in top_domains[:10]]
            },
            'summary': {
                'total_blocks': analysis_data['total_blocks'],
                'unique_domains': len(domain_analysis),
                'unique_hosts': len(analysis_data['unique_hosts'])
            }
        }

        return visualization_data

    except Exception as e:
        raise AnalyticsError(f"Failed to prepare visualization data: {str(e)}") from e


def generate_domain_analytics():
    """Generate complete domain analytics for the last 15 days."""
    try:
        # Fetch events
        events = fetch_firewall_events(days_back=15)

        if not events:
            return {
                'analysis': {},
                'visualization_data': {
                    'bar_chart': {'domains': [], 'visits': []},
                    'comparison_chart': {'domains': [], 'visits': [], 'unique_ips': []},
                    'summary': {'total_blocks': 0, 'unique_domains': 0, 'unique_hosts': 0}
                }
            }

        # Analyze events
        analysis_data = analyze_domain_events(events)

        # Prepare visualization data
        visualization_data = prepare_visualization_data(analysis_data)

        return {
            'analysis': analysis_data['domain_analysis'],
            'visualization_data': visualization_data
        }

    except (AnalyticsError, FirewallAPIError):
        raise
    except Exception as e:
        raise AnalyticsError(f"Failed to generate domain analytics: {str(e)}") from e
