import React, { useState, useEffect } from 'react';
import { Card, Descriptions, Tag, Tabs, List, Empty, Spin } from 'antd';
import { FunctionOutlined, FileTextOutlined } from '@ant-design/icons';
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8000';

const ContextPanel = ({ symbolId, onNavigate }) => {
  const [loading, setLoading] = useState(false);
  const [symbolDetails, setSymbolDetails] = useState(null);
  const [references, setReferences] = useState([]);
  const [activeTab, setActiveTab] = useState('details');

  useEffect(() => {
    if (symbolId) {
      fetchSymbolDetails();
      fetchReferences();
    } else {
      setSymbolDetails(null);
      setReferences([]);
    }
  }, [symbolId]);

  const fetchSymbolDetails = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/symbols/${symbolId}/details`);
      setSymbolDetails(res.data);
    } catch (err) {
      console.error('Failed to fetch symbol details:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchReferences = async () => {
    try {
      const res = await axios.get(`${API_BASE}/symbols/${symbolId}/references`);
      setReferences(res.data);
    } catch (err) {
      console.error('Failed to fetch references:', err);
    }
  };

  if (!symbolId) {
    return (
      <Card size="small" style={{ height: '100%' }}>
        <Empty description="Click on a symbol to view details" />
      </Card>
    );
  }

  if (loading) {
    return (
      <Card size="small" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin />
      </Card>
    );
  }

  const getComplexityColor = (complexity) => {
    if (!complexity) return 'default';
    if (complexity < 5) return 'green';
    if (complexity < 10) return 'orange';
    return 'red';
  };

  const items = [
    {
      key: 'details',
      label: 'Details',
      children: symbolDetails ? (
        <Descriptions size="small" column={1} bordered>
          <Descriptions.Item label="Name">
            <strong>{symbolDetails.name}</strong>
          </Descriptions.Item>
          <Descriptions.Item label="Kind">
            <Tag color="blue">{symbolDetails.kind}</Tag>
          </Descriptions.Item>
          {symbolDetails.signature && (
            <Descriptions.Item label="Signature">
              <code style={{ fontSize: '11px', wordBreak: 'break-all' }}>
                {symbolDetails.signature}
              </code>
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Location">
            {symbolDetails.file_path?.split(/[/\\]/).pop()} : {symbolDetails.line}
          </Descriptions.Item>
          {symbolDetails.kind === 'function' && (
            <Descriptions.Item label="Complexity">
              <Tag color={getComplexityColor(symbolDetails.cyclomatic_complexity)}>
                {symbolDetails.cyclomatic_complexity || 0}
              </Tag>
              {symbolDetails.cyclomatic_complexity >= 10 && (
                <span style={{ marginLeft: 8, fontSize: '11px', color: '#ff4d4f' }}>
                  High complexity - consider refactoring
                </span>
              )}
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Modifiers">
            {symbolDetails.is_static && <Tag>static</Tag>}
            {symbolDetails.is_extern && <Tag>extern</Tag>}
            {symbolDetails.is_definition ? <Tag color="green">definition</Tag> : <Tag>declaration</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="References">
            Callers: {symbolDetails.callers_count} | Callees: {symbolDetails.callees_count}
          </Descriptions.Item>
        </Descriptions>
      ) : <Empty />
    },
    {
      key: 'callers',
      label: `Callers (${references.filter(r => r.kind === 'call' && references.findIndex(ref => ref.id === r.id && ref.symbol_name !== symbolDetails?.name) !== -1).length})`,
      children: (
        <List
          size="small"
          dataSource={references.filter(r => {
            // 过滤出调用当前符号的引用
            return r.kind === 'call';
          })}
          renderItem={(ref) => (
            <List.Item
              style={{ cursor: 'pointer', padding: '8px 12px' }}
              onClick={() => onNavigate && onNavigate(ref.file_id, ref.line)}
            >
              <List.Item.Meta
                avatar={<FunctionOutlined />}
                title={<span style={{ fontSize: '13px' }}>{ref.symbol_name}</span>}
                description={
                  <span style={{ fontSize: '11px' }}>
                    {ref.file_path.split(/[/\\]/).pop()}:{ref.line}
                  </span>
                }
              />
              <Tag>{ref.kind}</Tag>
            </List.Item>
          )}
          locale={{ emptyText: 'No callers found' }}
        />
      )
    },
    {
      key: 'callees',
      label: `Callees (${references.filter(r => r.kind === 'call').length})`,
      children: (
        <List
          size="small"
          dataSource={references.filter(r => r.kind !== 'call')} // 这里的逻辑需要调整，应该是当前符号调用的
          renderItem={(ref) => (
            <List.Item
              style={{ cursor: 'pointer', padding: '8px 12px' }}
              onClick={() => onNavigate && onNavigate(ref.file_id, ref.line)}
            >
              <List.Item.Meta
                avatar={<FunctionOutlined />}
                title={<span style={{ fontSize: '13px' }}>{ref.symbol_name}</span>}
                description={
                  <span style={{ fontSize: '11px' }}>
                    {ref.file_path.split(/[/\\]/).pop()}:{ref.line}
                  </span>
                }
              />
              <Tag color="green">{ref.kind}</Tag>
            </List.Item>
          )}
          locale={{ emptyText: 'No callees found' }}
        />
      )
    }
  ];

  return (
    <Card
      size="small"
      style={{ height: '100%', overflow: 'auto' }}
      title={
        <span style={{ fontSize: '14px' }}>
          <FileTextOutlined /> Context & Relations
        </span>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        size="small"
        items={items}
      />
    </Card>
  );
};

export default ContextPanel;
