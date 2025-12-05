import React, { useState, useEffect } from 'react';
import { Modal, Progress, Typography, Space, Alert } from 'antd';
import { CheckCircleOutlined, LoadingOutlined, CloseCircleOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Text } = Typography;
const API_BASE = 'http://127.0.0.1:8000';

const ScanProgress = ({ projectId, visible, onComplete }) => {
  const [status, setStatus] = useState('pending');
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Initializing...');

  useEffect(() => {
    if (!visible || !projectId) return;

    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/projects/${projectId}/scan_status`);
        setStatus(res.data.status);
        setProgress(Math.round(res.data.progress * 100));
        setMessage(res.data.message || 'Scanning...');

        if (res.data.status === 'completed' || res.data.status === 'failed') {
          clearInterval(interval);
          setTimeout(() => {
            onComplete && onComplete(res.data.status === 'completed');
          }, 1000);
        }
      } catch (err) {
        console.error('Failed to fetch scan status:', err);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [visible, projectId]);

  const getStatusIcon = () => {
    switch (status) {
      case 'completed':
        return <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />;
      case 'failed':
        return <CloseCircleOutlined style={{ fontSize: 48, color: '#ff4d4f' }} />;
      default:
        return <LoadingOutlined style={{ fontSize: 48, color: '#1890ff' }} />;
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'completed':
        return 'success';
      case 'failed':
        return 'exception';
      default:
        return 'active';
    }
  };

  return (
    <Modal
      open={visible}
      title="Project Scanning"
      footer={null}
      closable={status === 'completed' || status === 'failed'}
      onCancel={() => onComplete && onComplete(status === 'completed')}
      width={500}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          {getStatusIcon()}
        </div>

        <Progress
          percent={progress}
          status={getStatusColor()}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
        />

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">{message}</Text>
        </div>

        {status === 'completed' && (
          <Alert
            message="Scan Completed Successfully"
            description="All files have been indexed. You can now explore the codebase."
            type="success"
            showIcon
          />
        )}

        {status === 'failed' && (
          <Alert
            message="Scan Failed"
            description={message}
            type="error"
            showIcon
          />
        )}
      </Space>
    </Modal>
  );
};

export default ScanProgress;
