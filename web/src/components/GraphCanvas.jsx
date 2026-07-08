import React, { useCallback, useEffect, useRef } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  Background,
  MarkerType,
  useReactFlow
} from '@xyflow/react';
import AgentNode from './nodes/AgentNode';

const nodeTypes = {
  agentNode: AgentNode,
};

const initialNodes = [
  { id: 'start', position: { x: 400, y: 50 }, data: { label: 'Ticket Arrives', status: 'idle' }, type: 'agentNode' }
];

function GraphCanvasInner({ wsEvents, currentHitl }) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { setCenter } = useReactFlow();
  
  // Track node positions dynamically
  const nodeRegistry = useRef({
    start: { x: 400, y: 50 },
    ingestion_node: { x: 400, y: 200 },
    triage_node: { x: 400, y: 350 },
    investigation_node: { x: 200, y: 500 },
    action_node: { x: 200, y: 650 },
    response_node: { x: 400, y: 650 },
    validation_node: { x: 400, y: 800 },
    finalizer_node: { x: 400, y: 950 },
    hitl_manual_resolution: { x: 600, y: 500 },
    hitl_approve_action: { x: 200, y: 800 },
    hitl_final_review: { x: 600, y: 800 },
  });

  const panToNode = useCallback((nodeId) => {
    const pos = nodeRegistry.current[nodeId];
    if (pos) {
      setCenter(pos.x + 100, pos.y + 50, { zoom: 1.2, duration: 1500 });
    }
  }, [setCenter]);

  // Process incoming websocket events
  useEffect(() => {
    if (!wsEvents || wsEvents.length === 0) {
      setNodes(initialNodes);
      setEdges([]);
      return;
    }
    
    const latestEvent = wsEvents[wsEvents.length - 1];
    
      if (latestEvent.type === 'node_update') {
      const nodeName = Object.keys(latestEvent.data)[0];
      
      // Hide internal LangGraph nodes from the UI
      if (nodeName === '__interrupt__') return;
      
      const outputs = latestEvent.data[nodeName];
      
      // Add the new node to the graph and mark it as stable
      setNodes((nds) => {
        const existingNode = nds.find(n => n.id === nodeName);
        if (existingNode) {
          return nds.map(n => n.id === nodeName ? { ...n, data: { ...n.data, status: 'stable', outputs } } : n);
        } else {
          return [...nds, {
            id: nodeName,
            position: nodeRegistry.current[nodeName] || { x: 400, y: 400 },
            type: 'agentNode',
            data: { label: nodeName.replace('_node', '').toUpperCase(), status: 'stable', outputs }
          }];
        }
      });
      
      // Edges are now strictly handled by the wsEvents edge generator below.
      
      panToNode(nodeName);
    }
    
  }, [wsEvents, panToNode, setNodes, setEdges]);
  
  // Custom edge adding logic that draws progressive edges based on the websocket history
  // and intelligently detects backward loops to break forward paths.
  useEffect(() => {
    if (!wsEvents || wsEvents.length === 0) {
      setEdges([]);
      return;
    }

    const activeEdges = [];
    let prevNode = 'start';

    for (const ev of wsEvents) {
      if (ev.type === 'node_update') {
        const currNode = Object.keys(ev.data)[0];
        
        if (currNode === prevNode) continue;
        
        const isRetry = prevNode === 'validation_node' && currNode === 'investigation_node';
        
        if (isRetry) {
          // Draw the feedback loop!
          activeEdges.push({
            id: `retry-${prevNode}-${currNode}-${activeEdges.length}`,
            source: prevNode,
            target: currNode,
            animated: true,
            style: { stroke: '#ef4444', strokeWidth: 3, strokeDasharray: '6,6' }, // Red dashed line
            markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' }
          });
          
          // Break the old forward edges (shatter the aborted path)
          for (let i = activeEdges.length - 1; i >= 0; i--) {
            const e = activeEdges[i];
            if (['investigation_node', 'action_node', 'response_node'].includes(e.source)) {
              activeEdges.splice(i, 1);
            }
          }
        } else {
          // Normal forward edge
          activeEdges.push({
            id: `e-${prevNode}-${currNode}-${activeEdges.length}`,
            source: prevNode,
            target: currNode,
            animated: true,
            style: { stroke: '#3b82f6', strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#3b82f6' }
          });
        }
        
        prevNode = currNode;
      }
    }
    
    setEdges(activeEdges);
  }, [wsEvents, setEdges]);

  // HITL Interrupt Handling
  useEffect(() => {
    if (currentHitl) {
      setNodes((nds) => {
        const existingNode = nds.find(n => n.id === currentHitl.node);
        if (!existingNode) {
          return [...nds, {
            id: currentHitl.node,
            position: nodeRegistry.current[currentHitl.node] || { x: 600, y: 500 },
            type: 'agentNode',
            data: { label: 'HUMAN IN THE LOOP', status: 'thinking' } // Keep it thinking until resolved
          }];
        }
        return nds;
      });
      panToNode(currentHitl.node);
    }
  }, [currentHitl, panToNode, setNodes]);

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#0f172a' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        zoomOnScroll={false}
        panOnScroll={true}
      >
        <Background color="#334155" gap={16} />
      </ReactFlow>
    </div>
  );
}

export default function GraphCanvas(props) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
