import React, { useEffect, useState, useRef } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import { Spin, Empty, Button, Tooltip, Select } from 'antd';
import { ZoomInOutlined, ZoomOutOutlined, GatewayOutlined, AimOutlined } from '@ant-design/icons';
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8000';

const RelationGraph = ({ projectId, symbolId, onNodeClick }) => {
  const [elements, setElements] = useState([]);
  const [loading, setLoading] = useState(false);
  const [depth, setDepth] = useState(2);
  const cyRef = useRef(null);

  useEffect(() => {
    if (projectId && symbolId) {
      fetchGraph(symbolId, depth);
    } else {
      setElements([]);
    }
  }, [projectId, symbolId, depth]);

  const fetchGraph = async (sid, d) => {
    setLoading(true);
    try {
      // Use the cross-file graph endpoint which supports depth
      const res = await axios.get(`${API_BASE}/graph/cross_file`, {
        params: {
          project_id: projectId,
          symbol_id: sid,
          depth: d
        }
      });
      
      if (res.data.elements && res.data.elements.nodes.length > 0) {
        setElements(CytoscapeComponent.normalizeElements(res.data.elements));
      } else {
        setElements([]);
      }
    } catch (err) {
      console.error("Failed to load relation graph", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCy = (cy) => {
    cyRef.current = cy;
    
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      const data = node.data();
      // Jump to code
      if (onNodeClick) {
        onNodeClick(data.id, data.line, data.file);
      }
    });

    // Center the target symbol if possible
    if (symbolId) {
       const targetNode = cy.getElementById(String(symbolId));
       if (targetNode.length > 0) {
           targetNode.select();
       }
    }
  };

  const fitGraph = () => {
    if (cyRef.current) cyRef.current.fit();
  };

  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}><Spin tip="Analyzing relationships..." /></div>;
  if (!symbolId) return <Empty description="Select a symbol to view relations" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginTop: 50 }} />;
  if (elements.length === 0) return <Empty description="No relationships found" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginTop: 50 }} />;

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10, display: 'flex', gap: 5, background: 'rgba(255,255,255,0.8)', padding: 5, borderRadius: 4 }}>
        <Select 
            size="small" 
            value={depth} 
            onChange={setDepth} 
            style={{ width: 100 }}
            options={[
                { value: 1, label: 'Depth: 1' },
                { value: 2, label: 'Depth: 2' },
                { value: 3, label: 'Depth: 3' },
                { value: 4, label: 'Depth: 4' }
            ]}
        />
        <Tooltip title="Fit View"><Button size="small" icon={<GatewayOutlined />} onClick={fitGraph} /></Tooltip>
      </div>

      <CytoscapeComponent
        elements={elements}
        cy={handleCy}
        style={{ width: '100%', height: '100%' }}
        layout={{
          name: 'cose',
          animate: true,
          nodeDimensionsIncludeLabels: true,
          idealEdgeLength: 100,
          edgeElasticity: 100,
          nodeRepulsion: 400000,
          padding: 30
        }}
        stylesheet={[
          {
            selector: 'node',
            style: {
              'label': 'data(label)',
              'width': 40,
              'height': 40,
              'background-color': 'data(color)',
              'color': '#333',
              'font-size': 10,
              'text-valign': 'center',
              'text-halign': 'center',
              'text-wrap': 'wrap',
              'text-max-width': 80
            }
          },
          {
            selector: ':selected',
            style: {
              'border-width': 3,
              'border-color': '#ff4d4f', // Red border for selected
              'width': 50,
              'height': 50
            }
          },
          {
            selector: 'edge',
            style: {
              'width': 2,
              'line-color': '#ccc',
              'target-arrow-color': '#ccc',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'label': 'data(label)',
              'font-size': 8,
              'color': '#999',
              'text-rotation': 'autorotate'
            }
          },
          {
            selector: 'edge[label="call"]',
            style: {
              'line-color': '#1890ff',
              'target-arrow-color': '#1890ff'
            }
          },
           {
            selector: 'edge[label="write"]',
            style: {
              'line-color': '#ff4d4f',
              'target-arrow-color': '#ff4d4f'
            }
          },
          {
            selector: 'edge[label="read"]',
            style: {
              'line-color': '#52c41a',
              'target-arrow-color': '#52c41a'
            }
          }
        ]}
      />
    </div>
  );
};

export default RelationGraph;
