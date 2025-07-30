// import React, { useContext, useState, useEffect, useRef } from 'react';
// import { FalconApiContext } from "../contexts/falcon-api-context";
// import { SlSpinner } from "@shoelace-style/shoelace/dist/react";
// import * as d3 from 'd3';

// function Relationship() {
//     const { falcon } = useContext(FalconApiContext);
//     const svgRef = useRef();
//     const [isLoading, setIsLoading] = useState(true);
//     const [error, setError] = useState(null);
//     const [relationshipData, setRelationshipData] = useState(null);
//     const [debugInfo, setDebugInfo] = useState([]);

//     const addDebugInfo = (message, data = null) => {
//         const timestamp = new Date().toISOString();
//         const logMessage = data 
//             ? `[${timestamp}] ${message}: ${JSON.stringify(data, null, 2)}`
//             : `[${timestamp}] ${message}`;
//         setDebugInfo(prev => [...prev, logMessage]);
//         console.log(logMessage);
//     };

//     const transformDataToGraph = (relationships) => {
//         const nodes = [];
//         const links = [];
//         const nodeMap = new Map();

//         relationships.forEach(rel => {
//             // Add category node
//             if (!nodeMap.has(rel.category_name)) {
//                 nodeMap.set(rel.category_name, true);
//                 nodes.push({
//                     id: rel.category_name,
//                     name: rel.category_name,
//                     type: 'category',
//                     level: 0
//                 });
//             }

//             // Add rule group node
//             if (!nodeMap.has(rel.rule_group_id)) {
//                 nodeMap.set(rel.rule_group_id, true);
//                 nodes.push({
//                     id: rel.rule_group_id,
//                     name: rel.rule_group_name,
//                     type: 'rule_group',
//                     level: 1
//                 });
//             }

//             // Add host group node
//             if (!nodeMap.has(rel.host_group_id)) {
//                 nodeMap.set(rel.host_group_id, true);
//                 nodes.push({
//                     id: rel.host_group_id,
//                     name: rel.host_group_name,
//                     type: 'host_group',
//                     level: 2
//                 });
//             }

//             // Add links
//             links.push({
//                 source: rel.category_name,
//                 target: rel.rule_group_id,
//                 type: 'category_to_rule',
//                 policy: rel.policy_name
//             });
//             links.push({
//                 source: rel.rule_group_id,
//                 target: rel.host_group_id,
//                 type: 'rule_to_host',
//                 policy: rel.policy_name
//             });
//         });

//         return { nodes, links };
//     };

//     const createGraph = (data) => {
//         if (!svgRef.current) return;

//         const width = 1200;
//         const height = 800;
//         const nodeRadius = 25;

//         // Clear existing SVG content
//         d3.select(svgRef.current).selectAll("*").remove();

//         // Create SVG
//         const svg = d3.select(svgRef.current)
//             .attr('width', width)
//             .attr('height', height)
//             .style('background-color', 'white');

//         // Add zoom capabilities
//         const g = svg.append('g');
//         const zoom = d3.zoom()
//             .scaleExtent([0.1, 4])
//             .on('zoom', (event) => g.attr('transform', event.transform));

//         svg.call(zoom);
//         // Initial zoom transform
//         svg.call(zoom.transform, d3.zoomIdentity.translate(width / 4, height / 4).scale(0.8));

//         // Define colors
//         const colors = {
//             category: '#e74c3c',
//             rule_group: '#3498db',
//             host_group: '#2ecc71'
//         };

//         // Create forces
//         const simulation = d3.forceSimulation(data.nodes)
//             .force('link', d3.forceLink(data.links)
//                 .id(d => d.id)
//                 .distance(200))
//             .force('charge', d3.forceManyBody().strength(-1000))
//             .force('x', d3.forceX(d => {
//                 if (d.type === 'category') return width * 0.2;
//                 if (d.type === 'rule_group') return width * 0.5;
//                 return width * 0.8;
//             }).strength(1))
//             .force('y', d3.forceY(height / 2).strength(0.3))
//             .force('collision', d3.forceCollide().radius(nodeRadius * 1.5));

//         // Create arrow markers
//         svg.append("defs").selectAll("marker")
//             .data(["end"])
//             .enter()
//             .append("marker")
//             .attr("id", "arrow")
//             .attr("viewBox", "0 -5 10 10")
//             .attr("refX", nodeRadius + 10)
//             .attr("refY", 0)
//             .attr("markerWidth", 6)
//             .attr("markerHeight", 6)
//             .attr("orient", "auto")
//             .append("path")
//             .attr("d", "M0,-5L10,0L0,5")
//             .attr("fill", "#999");

//         // Create links with curves
//         const links = g.append('g')
//             .selectAll('path')
//             .data(data.links)
//             .join('path')
//             .attr("stroke", "#999")
//             .attr("stroke-width", 2)
//             .attr("fill", "none")
//             .attr("marker-end", "url(#arrow)");

//         // Create nodes
//         const nodes = g.append('g')
//             .selectAll('g')
//             .data(data.nodes)
//             .join('g');

//         // Add circles to nodes
//         nodes.append('circle')
//             .attr('r', nodeRadius)
//             .style('fill', d => colors[d.type])
//             .style('stroke', '#fff')
//             .style('stroke-width', 2);

//         // Add labels to nodes
//         nodes.append('text')
//             .text(d => d.name)
//             .attr('text-anchor', 'middle')
//             .attr('dy', nodeRadius + 20)
//             .style('font-size', '12px')
//             .style('fill', '#333');

//         // Add drag behavior
//         const drag = d3.drag()
//             .on('start', dragstarted)
//             .on('drag', dragged)
//             .on('end', dragended);

//         nodes.call(drag);

//         function dragstarted(event) {
//             if (!event.active) simulation.alphaTarget(0.3).restart();
//             event.subject.fx = event.subject.x;
//             event.subject.fy = event.subject.y;
//         }

//         function dragged(event) {
//             event.subject.fx = event.x;
//             event.subject.fy = event.y;
//         }

//         function dragended(event) {
//             if (!event.active) simulation.alphaTarget(0);
//             event.subject.fx = null;
//             event.subject.fy = null;
//         }

//         // Update positions on each tick
//         simulation.on('tick', () => {
//             links.attr('d', d => {
//                 const dx = d.target.x - d.source.x;
//                 const dy = d.target.y - d.source.y;
//                 const dr = Math.sqrt(dx * dx + dy * dy);
//                 return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
//             });

//             nodes.attr('transform', d => `translate(${d.x},${d.y})`);
//         });

//         // Add tooltips
//         nodes.append('title')
//             .text(d => {
//                 return `Type: ${d.type}\nName: ${d.name}${d.policy ? '\nPolicy: ' + d.policy : ''}`;
//             });

//         // Add hover effects
//         nodes.on('mouseover', function(event, d) {
//             d3.select(this).select('circle')
//                 .transition()
//                 .duration(200)
//                 .attr('r', nodeRadius * 1.2);

//             // Highlight connected links and nodes
//             links.style('stroke-opacity', l => 
//                 (l.source.id === d.id || l.target.id === d.id) ? 1 : 0.1
//             );
//         }).on('mouseout', function() {
//             d3.select(this).select('circle')
//                 .transition()
//                 .duration(200)
//                 .attr('r', nodeRadius);

//             links.style('stroke-opacity', 0.6);
//         });
//     };

//     const fetchRelationships = async () => {
//         try {
//             addDebugInfo("Starting to fetch relationships");
//             setIsLoading(true);

//             const relationshipCollection = falcon.collection({
//                 collection: 'relationship'
//             });

//             const response = await relationshipCollection.list({ limit: 1000 });
//             addDebugInfo("List response", response);

//             const relationships = [];
//             for (const key of response.resources) {
//                 try {
//                     const record = await relationshipCollection.read(key);
//                     if (record) {
//                         relationships.push(record);
//                         addDebugInfo(`Added relationship for key ${key}`, record);
//                     }
//                 } catch (error) {
//                     addDebugInfo(`Error fetching data for key ${key}`, error.message);
//                 }
//             }

//             addDebugInfo("All relationships", relationships);

//             if (relationships.length > 0) {
//                 const graphData = transformDataToGraph(relationships);
//                 addDebugInfo("Graph data", graphData);
//                 setRelationshipData(graphData);
//             }

//         } catch (error) {
//             addDebugInfo("Error in fetchRelationships", error.message);
//             setError(error.message);
//         } finally {
//             setIsLoading(false);
//         }
//     };

//     useEffect(() => {
//         if (falcon) {
//             fetchRelationships();
//         }
//     }, [falcon]);

//     useEffect(() => {
//         if (relationshipData && svgRef.current) {
//             createGraph(relationshipData);
//         }
//     }, [relationshipData]);

//     if (isLoading) {
//         return (
//             <div className="flex items-center justify-center min-h-[600px]">
//                 <div className="text-center">
//                     <SlSpinner style={{ fontSize: '2rem' }} />
//                     <p className="mt-4 text-gray-600">Loading relationships...</p>
//                 </div>
//             </div>
//         );
//     }

//     return (
//         <div className="p-4">
//             <div className="bg-white rounded-lg shadow-lg p-6">
//                 <h2 className="text-xl font-bold mb-4">URL Blocking Relationships</h2>
                
//                 {/* Legend */}
//                 <div className="mb-4 flex space-x-4">
//                     <div className="flex items-center">
//                         <div className="w-4 h-4 rounded-full bg-[#e74c3c] mr-2"></div>
//                         <span>Categories</span>
//                     </div>
//                     <div className="flex items-center">
//                         <div className="w-4 h-4 rounded-full bg-[#3498db] mr-2"></div>
//                         <span>Rule Groups</span>
//                     </div>
//                     <div className="flex items-center">
//                         <div className="w-4 h-4 rounded-full bg-[#2ecc71] mr-2"></div>
//                         <span>Host Groups</span>
//                     </div>
//                 </div>

//                 {error && (
//                     <div className="mb-4 p-4 bg-red-50 text-red-600 rounded-lg">
//                         {error}
//                     </div>
//                 )}

//                 {/* Graph Container */}
//                 <div className="border rounded-lg overflow-hidden">
//                     <svg 
//                         ref={svgRef}
//                         style={{ 
//                             width: '100%', 
//                             height: '600px',
//                             backgroundColor: 'white'
//                         }}
//                     />
//                 </div>

//                 {/* Debug Information */}
//                 <div className="mt-4">
//                     <details>
//                         <summary className="cursor-pointer text-sm text-gray-600">
//                             Debug Information
//                         </summary>
//                         <pre className="mt-2 p-4 bg-gray-50 rounded-lg text-xs overflow-auto max-h-96">
//                             {debugInfo.join('\n')}
//                         </pre>
//                     </details>
//                 </div>
//             </div>
//         </div>
//     );
// }

// export { Relationship };


import React, { useContext, useState, useEffect, useRef } from 'react';
import { FalconApiContext } from "../contexts/falcon-api-context";
import { SlSpinner } from "@shoelace-style/shoelace/dist/react";
import * as d3 from 'd3';

// Add CSS styles
const graphStyles = {
    container: {
        width: '100%',
        height: 'calc(100vh - 200px)',
        minHeight: '900px',
        position: 'relative',
        backgroundColor: 'white',
        borderRadius: '8px',
        overflow: 'hidden'
    },
    svg: {
        width: '100%',
        height: '100%',
        display: 'block'
    }
};

function Relationship() {
    const { falcon } = useContext(FalconApiContext);
    const svgRef = useRef();
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [relationshipData, setRelationshipData] = useState(null);
    const [debugInfo, setDebugInfo] = useState([]);

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
            .attr('viewBox', [0, 0, width, height])
            .style('background-color', 'white');

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
            .attr("fill", "#999");

        // Create links with curves
        const links = g.append('g')
            .selectAll('path')
            .data(data.links)
            .join('path')
            .attr("stroke", "#999")
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
            .style('stroke', '#fff')
            .style('stroke-width', 3);

        // Add labels to nodes
        nodes.append('text')
            .text(d => d.name)
            .attr('text-anchor', 'middle')
            .attr('dy', nodeRadius + 25)
            .style('font-size', '14px')
            .style('fill', '#333')
            .style('font-weight', '500');

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
                const dr = Math.sqrt(dx * dx + dy * dy);
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

    useEffect(() => {
        if (relationshipData && svgRef.current) {
            createGraph(relationshipData);
        }
    }, [relationshipData]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[600px]">
                <div className="text-center">
                    <SlSpinner style={{ fontSize: '2rem' }} />
                    <p className="mt-4 text-gray-600">Loading relationships...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="p-4 w-full">
            <div className="bg-white rounded-lg shadow-lg p-6">
                <h2 className="text-xl font-bold mb-4">URL Blocking Relationships</h2>
                
                {/* Legend */}
                <div className="mb-4 flex space-x-4">
                    <div className="flex items-center">
                        <div className="w-4 h-4 rounded-full bg-[#e74c3c] mr-2"></div>
                        <span>Categories</span>
                    </div>
                    <div className="flex items-center">
                        <div className="w-4 h-4 rounded-full bg-[#3498db] mr-2"></div>
                        <span>Rule Groups</span>
                    </div>
                    <div className="flex items-center">
                        <div className="w-4 h-4 rounded-full bg-[#2ecc71] mr-2"></div>
                        <span>Host Groups</span>
                    </div>
                </div>

                {error && (
                    <div className="mb-4 p-4 bg-red-50 text-red-600 rounded-lg">
                        {error}
                    </div>
                )}

                {/* Graph Container */}
                <div style={graphStyles.container}>
                    <svg ref={svgRef} style={graphStyles.svg} />
                </div>

                {/* Debug Information */}
                <div className="mt-4">
                    <details>
                        <summary className="cursor-pointer text-sm text-gray-600">
                            Debug Information
                        </summary>
                        <pre className="mt-2 p-4 bg-gray-50 rounded-lg text-xs overflow-auto max-h-96">
                            {debugInfo.join('\n')}
                        </pre>
                    </details>
                </div>
            </div>
        </div>
    );
}

export { Relationship };
