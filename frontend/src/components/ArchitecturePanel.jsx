import React, { useState, useEffect, useRef } from 'react';
import { Drawer, Tabs, Card, List, Tag, Table, Empty, Spin, Space, Alert, Typography, Statistic, Row, Col, Button } from 'antd';
import {
  ApartmentOutlined,
  FireOutlined,
  WarningOutlined,
  BlockOutlined,
  CloseOutlined,
  GatewayOutlined
} from '@ant-design/icons';
import axios from 'axios';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import elk from 'cytoscape-elk';

cytoscape.use(elk);

const { Text, Title } = Typography;
const API_BASE = 'http://127.0.0.1:8000';

const STRUCTURE_LAYOUT = {
    name: 'elk',
    fit: true,
    padding: 20,
    animate: false,
    elk: {
        'algorithm': 'layered',
        'elk.direction': 'DOWN',
        'elk.spacing.nodeNode': '80',
        'elk.layered.spacing.nodeNodeBetweenLayers': '100',
        'elk.spacing.edgeNode': '30',
        'elk.edgeRouting': 'ORTHOGONAL',
        'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
        'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
        'elk.nodeLabels.placement': 'INSIDE H_CENTER V_TOP'
    }
};

const ArchitecturePanel = ({ projectId, visible, onClose, onFileSelect }) => {
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('hotspots');
  const cyRef = useRef(null);

  // Data states
  const [hotspots, setHotspots] = useState([]);
  const [circularDeps, setCircularDeps] = useState([]);
  const [structureElements, setStructureElements] = useState([]);

  useEffect(() => {
    if (visible && projectId) {
      fetchData();
    }
  }, [visible, projectId, activeTab]);

  const fetchData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'hotspots') {
        const res = await axios.get(`${API_BASE}/projects/${projectId}/architecture/hotspots`);
        setHotspots(res.data.hotspots || []);
      } else if (activeTab === 'circular') {
        const res = await axios.get(`${API_BASE}/projects/${projectId}/architecture/circular_dependencies`);
        setCircularDeps(res.data.circular_dependencies || []);
      } else if (activeTab === 'structure') {
        const res = await axios.get(`${API_BASE}/projects/${projectId}/architecture/structure_graph`);
        if (res.data.elements) {
            setStructureElements(CytoscapeComponent.normalizeElements(res.data.elements));
        }
      }
    } catch (err) {
      console.error('Failed to fetch architecture data:', err);
    } finally {
      setLoading(false);
    }
  };

  const renderHotspots = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Alert
        message="Code Complexity Hotspots"
        description="Files with high cyclomatic complexity that may need refactoring"
        type="warning"
        showIcon
        icon={<FireOutlined />}
      />

      <List
        dataSource={hotspots}
        loading={loading}
        renderItem={(item, index) => (
          <List.Item
            key={index}
            style={{ cursor: 'pointer' }}
            onClick={() => onFileSelect && onFileSelect(item.file_id)}
          >
            <List.Item.Meta
              avatar={
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: '50%',
                  background: item.avg_complexity > 10 ? '#ff4d4f' : item.avg_complexity > 5 ? '#faad14' : '#52c41a',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                  fontWeight: 'bold'
                }}>
                  {index + 1}
                </div>
              }
              title={
                <Space>
                  <Text strong>{item.path.split(/[/\\]/).pop()}</Text>
                  <Tag color="red">Complexity: {item.total_complexity}</Tag>
                </Space>
              }
              description={
                <Space size="large">
                  <Text type="secondary">Functions: {item.function_count}</Text>
                  <Text type="secondary">Avg Complexity: {item.avg_complexity.toFixed(1)}</Text>
                  <Text type="secondary">Symbols: {item.symbol_count}</Text>
                </Space>
              }
            />
          </List.Item>
        )}
        locale={{ emptyText: 'No hotspots found' }}
      />
    </Space>
  );

  const renderCircularDependencies = () => (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      {circularDeps.length > 0 ? (
        <>
          <Alert
            message={`Found ${circularDeps.length} Circular Dependency Cycle(s)`}
            description="Circular dependencies can make code harder to understand and maintain"
            type="error"
            showIcon
            icon={<WarningOutlined />}
          />

          {circularDeps.map((cycle, idx) => (
            <Card
              key={idx}
              size="small"
              title={`Cycle ${idx + 1} - ${cycle.files.length} files involved`}
              style={{ borderColor: '#ff4d4f' }}
            >
              <List
                size="small"
                dataSource={cycle.files}
                renderItem={(file) => (
                  <List.Item
                    style={{ cursor: 'pointer' }}
                    onClick={() => onFileSelect && onFileSelect(file.id)}
                  >
                    <Text code>{file.path.split(/[/\\]/).pop()}</Text>
                  </List.Item>
                )}
              />
            </Card>
          ))}
        </>
      ) : (
        <Empty
          image={<WarningOutlined style={{ fontSize: 64, color: '#52c41a' }} />}
          description={
            <Space direction="vertical">
              <Text strong>No Circular Dependencies Found</Text>
              <Text type="secondary">Your codebase has a clean dependency structure!</Text>
            </Space>
          }
        />
      )}
    </Space>
  );

  const renderStructureGraph = () => {
    return (
      <div style={{ width: '100%', height: '500px', position: 'relative', border: '1px solid #f0f0f0' }}>
         <Button 
            icon={<GatewayOutlined />} 
            style={{ position: 'absolute', top: 10, right: 10, zIndex: 10 }}
            onClick={() => cyRef.current && cyRef.current.fit()}
        >
            Fit
        </Button>
        {loading ? <div style={{ textAlign: 'center', paddingTop: 100 }}><Spin tip="Building structure graph..." /></div> : (
        <CytoscapeComponent
            elements={structureElements}
            cy={(cy) => {
                cyRef.current = cy;
                cy.on('tap', 'node', (evt) => {
                    const node = evt.target;
                    const data = node.data();
                    if (data.type === 'file' && onFileSelect) {
                        onFileSelect(parseInt(data.id));
                    }
                });
            }}
            style={{ width: '100%', height: '100%' }}
            layout={STRUCTURE_LAYOUT}
            stylesheet={[
                {
                    selector: 'node[type="directory"]',
                    style: {
                        'shape': 'round-rectangle',
                        'background-color': '#e6f7ff',
                        'background-opacity': 0.3,
                        'border-width': 1,
                        'border-color': '#91d5ff',
                        'label': 'data(label)',
                        'text-valign': 'top',
                        'text-halign': 'center',
                        'font-size': 14,
                        'font-weight': 'bold',
                        'color': '#0050b3'
                    }
                },
                {
                    selector: 'node[type="file"]',
                    style: {
                        'shape': 'ellipse',
                        'width': 30,
                        'height': 30,
                        'background-color': '#fff',
                        'border-width': 2,
                        'border-color': '#1890ff',
                        'label': 'data(label)',
                        'font-size': 10,
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'color': '#333'
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 1,
                        'line-color': '#ccc',
                        'target-arrow-color': '#ccc',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier'
                    }
                }
            ]}
        />
        )}
      </div>
    );
  };

  const items = [
    {
      key: 'hotspots',
      label: (
        <span>
          <FireOutlined /> Hotspots
        </span>
      ),
      children: renderHotspots()
    },
    {
      key: 'circular',
      label: (
        <span>
          <WarningOutlined /> Circular Deps
          {circularDeps.length > 0 && (
            <Tag color="red" style={{ marginLeft: 8 }}>{circularDeps.length}</Tag>
          )}
        </span>
      ),
      children: renderCircularDependencies()
    },
    {
      key: 'structure',
      label: (
        <span>
          <ApartmentOutlined /> Structure Graph
        </span>
      ),
      children: renderStructureGraph()
    }
  ];

  return (
    <Drawer
      title={
        <Space>
          <ApartmentOutlined />
          <span>Architecture Analysis</span>
        </Space>
      }
      placement="right"
      width={900}
      open={visible}
      onClose={onClose}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={items}
      />
    </Drawer>
  );
};

export default ArchitecturePanel;
