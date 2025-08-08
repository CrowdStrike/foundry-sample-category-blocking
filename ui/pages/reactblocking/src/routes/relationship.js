import React, { useContext, useState, useEffect, useRef } from 'react';
import { FalconApiContext } from "../contexts/falcon-api-context";
import { SlSpinner, SlCard, SlAlert } from "@shoelace-style/shoelace/dist/react";
import * as d3 from 'd3';

function Relationship() {
    const { falcon } = useContext(FalconApiContext);
    const svgRef = useRef();
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [relationshipData, setRelationshipData] = useState(null);
    const [debugInfo, setDebugInfo] = useState([]);
    const [isDarkMode, setIsDarkMode] = useState(false);

    // Function to check if dark mode is active
    const checkDarkMode = () => {
        return document.documentElement.classList.contains('theme-dark');
    };

    // Update theme detection when component mounts and when theme changes
    useEffect(() => {
        // Set initial state
        setIsDarkMode(checkDarkMode());

        // Create a mutation observer to detect theme changes
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'class') {
                    setIsDarkMode(checkDarkMode());
                }
            });
        });

        // Start observing document element for class changes
        observer.observe(document.documentElement, { attributes: true });

        // Cleanup observer on unmount
        return () => observer.disconnect();
    }, []);

    const addDebugInfo = (message, data = null) => {
        const timestamp = new Date().toISOString();
        const logMessage = data 
            ? `[${timestamp}] ${message}: ${JSON.stringify(data, null, 2)}`
            : `[${timestamp}] ${message}`;
        setDebugInfo(prev => [...prev, logMessage]);
        console.log(logMessage);
    };

    const transformDataToGraph = (relationships) => {
        const nodes = [];
        const links = [];
        const nodeMap = new Map();

        relationships.forEach(rel => {
            // Add category node
            if (!nodeMap.has(rel.category_name)) {
                nodeMap.set(rel.category_name, true);
                nodes.push({
                    id: rel.category_name,
                    name: rel.category_name,
                    type: 'category',
                    level: 0
                });
            }

            // Add rule group node
            if (!nodeMap.has(rel.rule_group_id)) {
                nodeMap.set(rel.rule_group_id, true);
                nodes.push({
                    id: rel.rule_group_id,
                    name: rel.rule_group_name,
                    type: 'rule_group',
                    level: 1
                });
            }

            // Add host group node
            if (!nodeMap.has(rel.host_group_id)) {
                nodeMap.set(rel.host_group_id, true);
                nodes.push({
                    id: rel.host_group_id,
                    name: rel.host_group_name,
                    type: 'host_group',
                    level: 2
                });
            }

            // Add links
            links.push({
                source: rel.category_name,
                target: rel.rule_group_id,
                type: 'category_to_rule',
                policy: rel.policy_name
            });
            links.push({
                source: rel.rule_group_id,
                target: rel.host_group_id,
                type: 'rule_to_host',
                policy: rel.policy_name
            });
        });

        return { nodes, links };
    };

    const createGraph = (data) => {
        if (!svgRef.current) return;

        console.log("Creating graph in", isDarkMode ? "dark mode" : "light mode");
        
        // Set dimensions
        const width = 2000;
        const height = 1200;
        const nodeRadius = 35;
        const spacing = {
            category: width * 0.15,
            ruleGroup: width * 0.5,
            hostGroup: width * 0.85
        };

        // Clear existing SVG content
        d3.select(svgRef.current).selectAll("*").remove();

        // Create SVG
        const svg = d3.select(svgRef.current)
            .attr('width', '100%')
            .attr('height', '100%')
            .attr('viewBox', [0, 0, width, height]);

        // Add zoom capabilities
        const g = svg.append('g');
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => g.attr('transform', event.transform));

        svg.call(zoom);
        svg.call(zoom.transform, 
            d3.zoomIdentity
                .translate(width * 0.1, height * 0.1)
                .scale(0.6)
        );

        // Define colors
        const colors = {
            category: '#e74c3c',
            rule_group: '#3498db',
            host_group: '#2ecc71'
        };

        // Create forces
        const simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.links)
                .id(d => d.id)
                .distance(400))
            .force('charge', d3.forceManyBody().strength(-3000))
            .force('x', d3.forceX(d => {
                if (d.type === 'category') return spacing.category;
                if (d.type === 'rule_group') return spacing.ruleGroup;
                return spacing.hostGroup;
            }).strength(1))
            .force('y', d3.forceY(height / 2).strength(0.2))
            .force('collision', d3.forceCollide().radius(nodeRadius * 3));

        // Create arrow markers
        svg.append("defs").selectAll("marker")
            .data(["end"])
            .enter()
            .append("marker")
            .attr("id", "arrow")
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", nodeRadius + 15)
            .attr("refY", 0)
            .attr("markerWidth", 8)
            .attr("markerHeight", 8)
            .attr("orient", "auto")
            .append("path")
            .attr("d", "M0,-5L10,0L0,5")
            .attr("fill", isDarkMode ? "#aaaaaa" : "#666666");

        // Create links with curves
        const links = g.append('g')
            .selectAll('path')
            .data(data.links)
            .join('path')
            .attr("stroke", isDarkMode ? "#aaaaaa" : "#666666")
            .attr("stroke-width", 2)
            .attr("fill", "none")
            .attr("marker-end", "url(#arrow)");

        // Create nodes
        const nodes = g.append('g')
            .selectAll('g')
            .data(data.nodes)
            .join('g');

        // Add circles to nodes
        nodes.append('circle')
            .attr('r', nodeRadius)
            .style('fill', d => colors[d.type])
            .style('stroke', isDarkMode ? '#444444' : '#ffffff')
            .style('stroke-width', 3);

        // Add labels to nodes with proper contrast for both themes
        nodes.append('text')
            .text(d => d.name)
            .attr('text-anchor', 'middle')
            .attr('dy', nodeRadius + 25)
            .attr('class', 'node-label')
            .style('font-size', '16px')
            .style('font-weight', '600')
            .style('fill', isDarkMode ? '#ffffff' : '#333333')
            .style('stroke', isDarkMode ? '#000000' : 'none')
            .style('stroke-width', isDarkMode ? '0.5px' : '0')
            .style('paint-order', 'stroke fill');

        // Add drag behavior
        const drag = d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended);

        nodes.call(drag);

        function dragstarted(event) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        // Update positions on each tick
        simulation.on('tick', () => {
            links.attr('d', d => {
                const dx = d.target.x - d.source.x;
                const dy = d.target.y - d.source.y;
                const dr = Math.sqrt(dx * dx + dy * dy) * 1.5;
                return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
            });

            nodes.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Add tooltips
        nodes.append('title')
            .text(d => `${d.type}: ${d.name}`);

        // Add hover effects
        nodes.on('mouseover', function(event, d) {
            d3.select(this).select('circle')
                .transition()
                .duration(200)
                .attr('r', nodeRadius * 1.2);

            links.style('stroke-opacity', l => 
                (l.source.id === d.id || l.target.id === d.id) ? 1 : 0.1
            );
        }).on('mouseout', function() {
            d3.select(this).select('circle')
                .transition()
                .duration(200)
                .attr('r', nodeRadius);

            links.style('stroke-opacity', 0.6);
        });
    };

    const fetchRelationships = async () => {
        try {
            addDebugInfo("Starting to fetch relationships");
            setIsLoading(true);

            const relationshipCollection = falcon.collection({
                collection: 'relationship'
            });

            const response = await relationshipCollection.list({ limit: 1000 });
            addDebugInfo("List response", response);

            const relationships = [];
            for (const key of response.resources) {
                try {
                    const record = await relationshipCollection.read(key);
                    if (record) {
                        relationships.push(record);
                        addDebugInfo(`Added relationship for key ${key}`, record);
                    }
                } catch (error) {
                    addDebugInfo(`Error fetching data for key ${key}`, error.message);
                }
            }

            addDebugInfo("All relationships", relationships);

            if (relationships.length > 0) {
                const graphData = transformDataToGraph(relationships);
                addDebugInfo("Graph data", graphData);
                setRelationshipData(graphData);
            }

        } catch (error) {
            addDebugInfo("Error in fetchRelationships", error.message);
            setError(error.message);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (falcon) {
            fetchRelationships();
        }
    }, [falcon]);

    // Recreate graph when data changes or theme changes
    useEffect(() => {
        if (relationshipData && svgRef.current) {
            console.log("Recreating graph due to dark mode change:", isDarkMode);
            createGraph(relationshipData);
        }
    }, [relationshipData, isDarkMode]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[600px]">
                <div className="text-center">
                    <SlSpinner style={{ fontSize: '2rem' }} />
                    <p className="mt-4">Loading relationships...</p>
                </div>
            </div>
        );
    }

    // Define styles that adapt to theme
    const graphStyles = {
        container: {
            width: '100%',
            height: 'calc(100vh - 200px)',
            minHeight: '900px',
            position: 'relative',
            backgroundColor: 'var(--sl-panel-background-color)',
            borderRadius: '8px',
            overflow: 'hidden'
        },
        svg: {
            width: '100%',
            height: '100%',
            display: 'block'
        }
    };

    return (
        <div className="p-4 w-full">
            <SlCard>
                <div slot="header">
                    <h2 className="text-lg font-semibold text-left mb-4" style={{ color: 'var(--sl-color-neutral-1000)' }}>
                        Category-Based Access Control Network
                    </h2>
                </div>

                {/* Legend */}
                <div className="mb-4 flex space-x-8">
                    <div className="flex items-center">
                        <div style={{ 
                            width: '16px', 
                            height: '16px', 
                            borderRadius: '50%', 
                            backgroundColor: '#e74c3c',
                            marginRight: '8px'
                        }}></div>
                        <span>Categories</span>
                    </div>
                    <div className="flex items-center">
                        <div style={{ 
                            width: '16px', 
                            height: '16px', 
                            borderRadius: '50%', 
                            backgroundColor: '#3498db',
                            marginRight: '8px'
                        }}></div>
                        <span>Rule Groups</span>
                    </div>
                    <div className="flex items-center">
                        <div style={{ 
                            width: '16px', 
                            height: '16px', 
                            borderRadius: '50%', 
                            backgroundColor: '#2ecc71',
                            marginRight: '8px'
                        }}></div>
                        <span>Host Groups</span>
                    </div>
                </div>

                {error && (
                    <SlAlert variant="danger" className="mb-4">
                        {error}
                    </SlAlert>
                )}

                {/* Graph Container */}
                <div style={graphStyles.container}>
                    <svg ref={svgRef} style={graphStyles.svg} />
                </div>
            </SlCard>
        </div>
    );
}

export { Relationship };
