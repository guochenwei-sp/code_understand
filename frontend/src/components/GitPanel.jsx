import React, { useState, useEffect } from 'react';
import { Card, List, Tag, Button, Space, Drawer, Typography, Divider, Empty, Spin, message } from 'antd';
import {
  BranchesOutlined,
  ClockCircleOutlined,
  UserOutlined,
  FileTextOutlined,
  CloseOutlined
} from '@ant-design/icons';
import axios from 'axios';

const { Text, Paragraph } = Typography;
const API_BASE = 'http://127.0.0.1:8000';

const GitPanel = ({ projectId, currentFile, visible, onClose }) => {
  const [commits, setCommits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCommit, setSelectedCommit] = useState(null);
  const [diffContent, setDiffContent] = useState('');
  const [changedFiles, setChangedFiles] = useState([]);
  const [showDiff, setShowDiff] = useState(false);

  useEffect(() => {
    if (visible && projectId) {
      fetchCommits();
    }
  }, [visible, projectId, currentFile]);

  const fetchCommits = async () => {
    setLoading(true);
    try {
      const params = { max_count: 50 };
      if (currentFile) {
        // 获取当前文件的相对路径
        params.file_path = currentFile.path;
      }
      const res = await axios.get(`${API_BASE}/projects/${projectId}/git/commits`, { params });
      setCommits(res.data.commits || []);
    } catch (err) {
      if (err.response?.status === 400) {
        message.warning('This project is not a Git repository');
      } else {
        message.error('Failed to load Git history');
      }
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const viewCommitDetails = async (commit) => {
    setSelectedCommit(commit);
    setShowDiff(true);

    try {
      // 获取 diff
      const diffRes = await axios.get(`${API_BASE}/projects/${projectId}/git/diff`, {
        params: { commit_hash: commit.hash }
      });
      setDiffContent(diffRes.data.diff);

      // 获取变更文件
      const filesRes = await axios.get(`${API_BASE}/projects/${projectId}/git/changed_files`, {
        params: { commit_hash: commit.hash }
      });
      setChangedFiles(filesRes.data.changed_files || []);
    } catch (err) {
      message.error('Failed to load commit details');
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'M': return 'blue';
      case 'A': return 'green';
      case 'D': return 'red';
      default: return 'default';
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'M': return 'Modified';
      case 'A': return 'Added';
      case 'D': return 'Deleted';
      default: return status;
    }
  };

  return (
    <>
      <Drawer
        title={
          <Space>
            <BranchesOutlined />
            <span>Git History</span>
            {currentFile && (
              <Tag color="blue">{currentFile.path.split(/[/\\]/).pop()}</Tag>
            )}
          </Space>
        }
        placement="right"
        width={600}
        open={visible}
        onClose={onClose}
        extra={
          <Button type="text" icon={<CloseOutlined />} onClick={onClose} />
        }
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: '50px' }}>
            <Spin size="large" />
          </div>
        ) : commits.length === 0 ? (
          <Empty description="No commit history available" />
        ) : (
          <List
            dataSource={commits}
            renderItem={(commit) => (
              <List.Item
                key={commit.hash}
                style={{ cursor: 'pointer' }}
                onClick={() => viewCommitDetails(commit)}
                actions={[
                  <Button size="small" type="link">View</Button>
                ]}
              >
                <List.Item.Meta
                  avatar={<UserOutlined style={{ fontSize: 20, color: '#1890ff' }} />}
                  title={
                    <Space direction="vertical" size={0}>
                      <Text strong>{commit.message}</Text>
                      <Space size="small">
                        <Tag color="orange">{commit.hash.substring(0, 7)}</Tag>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          <UserOutlined /> {commit.author_name}
                        </Text>
                      </Space>
                    </Space>
                  }
                  description={
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <ClockCircleOutlined /> {new Date(commit.date).toLocaleString()}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>

      {/* Diff Viewer Drawer */}
      <Drawer
        title={
          <Space>
            <FileTextOutlined />
            <span>Commit Details</span>
            {selectedCommit && (
              <Tag color="orange">{selectedCommit.hash.substring(0, 7)}</Tag>
            )}
          </Space>
        }
        placement="right"
        width={800}
        open={showDiff}
        onClose={() => setShowDiff(false)}
      >
        {selectedCommit && (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <div>
              <Paragraph>
                <Text strong>{selectedCommit.message}</Text>
              </Paragraph>
              <Space>
                <Text type="secondary">
                  <UserOutlined /> {selectedCommit.author_name}
                </Text>
                <Text type="secondary">
                  <ClockCircleOutlined /> {new Date(selectedCommit.date).toLocaleString()}
                </Text>
              </Space>
            </div>

            <Divider />

            {changedFiles.length > 0 && (
              <>
                <div>
                  <Text strong>Changed Files ({changedFiles.length})</Text>
                  <List
                    size="small"
                    dataSource={changedFiles}
                    renderItem={(file) => (
                      <List.Item>
                        <Space>
                          <Tag color={getStatusColor(file.status)}>
                            {getStatusText(file.status)}
                          </Tag>
                          <Text code style={{ fontSize: 12 }}>{file.path}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </div>
                <Divider />
              </>
            )}

            <div>
              <Text strong>Diff</Text>
              <pre
                style={{
                  background: '#f5f5f5',
                  padding: '16px',
                  borderRadius: '4px',
                  overflow: 'auto',
                  maxHeight: '60vh',
                  fontSize: '12px',
                  fontFamily: 'Monaco, Consolas, monospace'
                }}
              >
                {diffContent || 'No diff available'}
              </pre>
            </div>
          </Space>
        )}
      </Drawer>
    </>
  );
};

export default GitPanel;
