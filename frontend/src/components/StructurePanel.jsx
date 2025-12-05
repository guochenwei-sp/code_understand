import React, { useEffect, useState } from 'react';
import { List, Typography, Spin, Empty, Tag, Collapse } from 'antd';
import { FunctionOutlined, FieldTimeOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Text } = Typography;
const { Panel } = Collapse;

const API_BASE = 'http://127.0.0.1:8000';

const StructurePanel = ({ fileId, onSymbolSelect }) => {
  const [symbols, setSymbols] = useState({ functions: [], variables: [], others: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (fileId) {
      fetchSymbols(fileId);
    } else {
      setSymbols({ functions: [], variables: [], others: [] });
    }
  }, [fileId]);

  const fetchSymbols = async (fid) => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/files/${fid}/symbols`);
      const allSymbols = res.data;
      
      const grouped = {
        functions: [],
        variables: [],
        others: []
      };

      allSymbols.forEach(s => {
        if (s.kind === 'function') {
          grouped.functions.push(s);
        } else if (s.kind === 'variable' || s.kind === 'field' || s.kind === 'parm') {
          grouped.variables.push(s);
        } else {
          grouped.others.push(s);
        }
      });

      // Sort by line number
      grouped.functions.sort((a, b) => a.line - b.line);
      grouped.variables.sort((a, b) => a.line - b.line);
      grouped.others.sort((a, b) => a.line - b.line);

      setSymbols(grouped);
    } catch (err) {
      console.error("Failed to load structure", err);
    } finally {
      setLoading(false);
    }
  };

  const renderItem = (item) => (
    <List.Item 
      className="structure-item"
      onClick={() => onSymbolSelect(item)}
      style={{ cursor: 'pointer', padding: '4px 8px', fontSize: '12px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
        <Text ellipsis style={{ maxWidth: '180px' }}>{item.name}</Text>
        <Text type="secondary" style={{ fontSize: '10px' }}>:{item.line}</Text>
      </div>
    </List.Item>
  );

  if (loading) return <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>;
  if (!fileId) return <Empty description="No file selected" image={Empty.PRESENTED_IMAGE_SIMPLE} />;

  return (
    <div className="structure-panel" style={{ height: '100%', overflowY: 'auto' }}>
      <Collapse defaultActiveKey={['1', '2']} ghost size="small">
        <Panel header={`Functions (${symbols.functions.length})`} key="1">
          <List
            size="small"
            dataSource={symbols.functions}
            renderItem={renderItem}
            locale={{ emptyText: 'No functions' }}
          />
        </Panel>
        <Panel header={`Variables (${symbols.variables.length})`} key="2">
          <List
            size="small"
            dataSource={symbols.variables}
            renderItem={renderItem}
            locale={{ emptyText: 'No variables' }}
          />
        </Panel>
        {symbols.others.length > 0 && (
          <Panel header={`Others (${symbols.others.length})`} key="3">
            <List
              size="small"
              dataSource={symbols.others}
              renderItem={renderItem}
            />
          </Panel>
        )}
      </Collapse>
    </div>
  );
};

export default StructurePanel;
