import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Layout, Menu, Button, Card, Table, Modal, Input, Form,
  message, List, Typography, Select, Tag, Empty, Spin, AutoComplete, Tree, Tooltip, Tabs
} from 'antd';
import {
  RocketOutlined, FolderOpenOutlined, PlusOutlined,
  ReloadOutlined, FileTextOutlined, ArrowLeftOutlined, SearchOutlined, AppstoreOutlined,
  FolderOutlined, BranchesOutlined, ApartmentOutlined, FireOutlined
} from '@ant-design/icons';
import axios from 'axios';
import CytoscapeComponent from 'react-cytoscapejs';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';

// Import new components
import ContextPanel from './components/ContextPanel';
import ScanProgress from './components/ScanProgress';
import GitPanel from './components/GitPanel';
import ArchitecturePanel from './components/ArchitecturePanel';
import StructurePanel from './components/StructurePanel';
import RelationGraph from './components/RelationGraph';

// Configure Monaco Editor
loader.config({ monaco });

const { Header, Content, Sider } = Layout;
const { Title, Text } = Typography;
const { Option } = Select;
const { DirectoryTree } = Tree;

const API_BASE = 'http://127.0.0.1:8000';

const ipcRenderer = window.require && window.require('electron') ? window.require('electron').ipcRenderer : null;

const App = () => {
  // --- Global State ---
  const [view, setView] = useState('project-list');
  const [currentProject, setCurrentProject] = useState(null);

  // --- Project List State ---
  const [projects, setProjects] = useState([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [loadingProjects, setLoadingProjects] = useState(false);

  // --- Project Detail State ---
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');

  const [graphElements, setGraphElements] = useState(null);
  const [filterKind, setFilterKind] = useState('function');

  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);

  // Search State
  const [searchResults, setSearchResults] = useState([]);

  // Form State
  const [rootPathInput, setRootPathInput] = useState('');

  // DSM State
  const [isDSMVisible, setIsDSMVisible] = useState(false);
  const [dsmData, setDsmData] = useState(null);
  const [loadingDSM, setLoadingDSM] = useState(false);

  // New: Context Panel State
  const [selectedSymbolId, setSelectedSymbolId] = useState(null);
  const [showContextPanel, setShowContextPanel] = useState(true);

  // New: Scan Progress State
  const [showScanProgress, setShowScanProgress] = useState(false);

  // New: Git Panel State
  const [showGitPanel, setShowGitPanel] = useState(false);

  // New: Architecture Panel State
  const [showArchPanel, setShowArchPanel] = useState(false);

  const [sidebarMode, setSidebarMode] = useState('files');

  // Refs
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const cyRef = useRef(null);
  const pendingJumpRef = useRef(null);
  const treeContainerRef = useRef(null);
  const [treeHeight, setTreeHeight] = useState(500);

  // === Lifecycle ===
  useEffect(() => {
    if (view === 'project-list') {
      fetchProjects();
    }
  }, [view]);

  useEffect(() => {
    let interval;
    if (currentProject) {
      fetchFiles(currentProject.id);
      interval = setInterval(() => {
        fetchFiles(currentProject.id, true);
      }, 10000);
    }
    return () => clearInterval(interval);
  }, [currentProject]);

  useEffect(() => {
    if (view === 'project-detail' && treeContainerRef.current) {
      const observer = new ResizeObserver(entries => {
        for (let entry of entries) {
          setTreeHeight(entry.contentRect.height);
        }
      });
      observer.observe(treeContainerRef.current);
      return () => observer.disconnect();
    }
  }, [view, loadingFiles]);

  useEffect(() => {
    if (selectedFile) {
      fetchGraph(selectedFile.id);
      fetchFileContent(selectedFile.id);
      analyzeFile(selectedFile.id);
    } else {
      setFileContent('');
      setGraphElements(null);
    }
  }, [selectedFile, filterKind]);

  // Handle pending jump
  useEffect(() => {
    if (!loadingContent && fileContent && pendingJumpRef.current && editorRef.current) {
      const line = pendingJumpRef.current;
      try {
        editorRef.current.revealLineInCenter(line);
        editorRef.current.setPosition({ lineNumber: line, column: 1 });
        editorRef.current.focus();
        editorRef.current.createDecorationsCollection([
          {
            range: new window.monaco.Range(line, 1, line, 1),
            options: { isWholeLine: true, className: 'myLineDecoration' }
          }
        ]);
      } catch (e) { console.error(e); }
      pendingJumpRef.current = null;
    }
  }, [loadingContent, fileContent]);

  // === Helper: Build Tree Data ===
  const treeData = useMemo(() => {
    if (!currentProject || files.length === 0) return [];

    const rootPath = currentProject.root_path.replace(/\\/g, '/');
    const tree = [];

    const findOrCreateNode = (nodes, name, key) => {
      let node = nodes.find(n => n.title === name);
      if (!node) {
        node = { title: name, key: key, children: [], isLeaf: false };
        nodes.push(node);
      }
      return node;
    };

    files.forEach(file => {
      const fullPath = file.path.replace(/\\/g, '/');

      let relative = fullPath;
      if (fullPath.startsWith(rootPath)) {
        relative = fullPath.substring(rootPath.length);
      }
      if (relative.startsWith('/')) relative = relative.substring(1);

      const parts = relative.split('/');
      const fileName = parts.pop();

      let currentLevel = tree;
      let currentKey = rootPath;

      parts.forEach(part => {
        currentKey += '/' + part;
        const node = findOrCreateNode(currentLevel, part, currentKey);
        currentLevel = node.children;
      });

      currentLevel.push({
        title: fileName,
        key: `file-${file.id}`,
        isLeaf: true,
        icon: <FileTextOutlined />,
        data: file
      });
    });

    const sortNodes = (nodes) => {
      nodes.sort((a, b) => {
        if (a.isLeaf === b.isLeaf) return a.title.localeCompare(b.title);
        return a.isLeaf ? 1 : -1;
      });
      nodes.forEach(n => {
        if (n.children) sortNodes(n.children);
      });
    };
    sortNodes(tree);

    return tree;
  }, [files, currentProject]);

  // === API Calls (继续使用之前的实现，但增强) ===
  const fetchProjects = async () => {
    setLoadingProjects(true);
    try {
      const res = await axios.get(`${API_BASE}/projects/`);
      setProjects(res.data);
    } catch (err) {
      message.error('Failed to load projects');
    } finally {
      setLoadingProjects(false);
    }
  };

  const createProject = async (values) => {
    try {
      const res = await axios.post(`${API_BASE}/projects/`, values);
      message.success('Project created');
      setIsModalVisible(false);
      form.resetFields();
      fetchProjects();
      openProject(res.data);
      triggerScan(res.data.id);
    } catch (err) {
      message.error('Failed to create project: ' + (err.response?.data?.detail || err.message));
    }
  };

  const triggerScan = async (projectId) => {
    try {
      await axios.post(`${API_BASE}/projects/${projectId}/scan`);
      message.info('Scanning started...');
      setShowScanProgress(true);  // Show progress modal
    } catch (err) {
      message.error('Failed to start scan');
    }
  };

  const fetchFiles = async (projectId, silent = false) => {
    if (!silent) setLoadingFiles(true);
    try {
      const res = await axios.get(`${API_BASE}/projects/${projectId}/files`);
      setFiles(res.data);
    } catch (err) {
      if (!silent) message.error('Failed to load files');
    } finally {
      if (!silent) setLoadingFiles(false);
    }
  };

  const fetchGraph = async (fileId) => {
    setLoadingGraph(true);
    setGraphElements(null);
    try {
      const url = filterKind
        ? `${API_BASE}/graph/file?file_id=${fileId}&kind=${filterKind}`
        : `${API_BASE}/graph/file?file_id=${fileId}`;

      const res = await axios.get(url);
      if (res.data.elements && res.data.elements.nodes.length > 0) {
        setGraphElements(CytoscapeComponent.normalizeElements(res.data.elements));
      } else {
        setGraphElements(null);
      }
    } catch (err) {
      message.error('Failed to load graph');
    } finally {
      setLoadingGraph(false);
    }
  };

  const fetchFileContent = async (fileId) => {
    setLoadingContent(true);
    try {
      const res = await axios.get(`${API_BASE}/files/${fileId}/content`);
      setFileContent(res.data.content);
    } catch (err) {
      message.error('Failed to load file content');
      setFileContent('// Failed to load content');
    } finally {
      setLoadingContent(false);
    }
  };

  const analyzeFile = async (fileId) => {
    try {
      const res = await axios.get(`${API_BASE}/files/${fileId}/analyze`);
      const findings = res.data;

      if (monacoRef.current && editorRef.current) {
        const model = editorRef.current.getModel();
        const markers = findings.map(f => ({
          startLineNumber: f.line,
          startColumn: 1,
          endLineNumber: f.line,
          endColumn: 1000,
          message: f.message,
          severity: f.severity === 'error' ? 8 : 4
        }));
        monacoRef.current.editor.setModelMarkers(model, "owner", markers);
      }
    } catch (err) {
      console.error("Analysis failed", err);
    }
  };

  const fetchDSM = async () => {
    setLoadingDSM(true);
    try {
      const res = await axios.get(`${API_BASE}/projects/${currentProject.id}/dsm`);
      setDsmData(res.data);
    } catch (err) {
      message.error("Failed to load DSM");
    } finally {
      setLoadingDSM(false);
    }
  };

  const handleSearch = async (value) => {
    if (!value || value.length < 2) {
      setSearchResults([]);
      return;
    }
    try {
      const res = await axios.get(`${API_BASE}/search`, {
        params: { q: value, project_id: currentProject.id }
      });
      const options = res.data.map(item => ({
        value: item.name,
        label: (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{item.name}</span>
            <span style={{ color: '#888', fontSize: '12px' }}>
              {item.kind} • {item.file_path.split('\\').pop()}:{item.line}
              {item.complexity > 0 && ` • C:${item.complexity}`}
            </span>
          </div>
        ),
        item: item
      }));
      setSearchResults(options);
    } catch (err) {
      console.error(err);
    }
  };

  const onSelectSymbol = (value, option) => {
    const symbol = option.item;
    const targetFile = files.find(f => f.id === symbol.file_id) || { id: symbol.file_id, path: symbol.file_path };
    setSelectedFile(targetFile);
    pendingJumpRef.current = symbol.line;
    // 同时设置选中的符号以显示详情
    setSelectedSymbolId(symbol.id);
  };

  const handleBrowseDirectory = async () => {
    if (ipcRenderer) {
      const result = await ipcRenderer.invoke('dialog:openDirectory');
      if (result) {
        form.setFieldsValue({ root_path: result });
        setRootPathInput(result);
      }
    } else {
      message.warn("Directory browsing is only available in Electron desktop app.");
    }
  };

  // === New: Monaco Editor Providers ===
  const setupMonacoProviders = (editor, monaco) => {
    // Go to Definition Provider
    monaco.languages.registerDefinitionProvider('c', {
      provideDefinition: async (model, position) => {
        try {
          const word = model.getWordAtPosition(position);
          if (!word) return null;

          const results = await axios.get(`${API_BASE}/search`, {
            params: { q: word.word, project_id: currentProject.id, limit: 10 }
          });

          if (results.data.length === 0) return null;

          // 返回所有匹配的定义位置
          return results.data
            .filter(r => r.is_definition)
            .map(r => ({
              uri: monaco.Uri.file(r.file_path),
              range: new monaco.Range(r.line, 1, r.line, 1000)
            }));
        } catch (err) {
          console.error('Definition provider error:', err);
          return null;
        }
      }
    });

    // Hover Provider
    monaco.languages.registerHoverProvider('c', {
      provideHover: async (model, position) => {
        try {
          const word = model.getWordAtPosition(position);
          if (!word) return null;

          const results = await axios.get(`${API_BASE}/search`, {
            params: { q: word.word, project_id: currentProject.id, limit: 1 }
          });

          if (results.data.length === 0) return null;

          const symbol = results.data[0];
          const contents = [
            { value: `**${symbol.kind}** \`${symbol.name}\`` }
          ];

          if (symbol.signature) {
            contents.push({ value: `\`\`\`c\n${symbol.signature}\n\`\`\`` });
          }

          if (symbol.complexity > 0) {
            contents.push({ value: `Cyclomatic Complexity: **${symbol.complexity}**` });
          }

          contents.push({ value: `Location: ${symbol.file_path.split(/[/\\]/).pop()}:${symbol.line}` });

          return {
            range: new monaco.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn
            ),
            contents: contents
          };
        } catch (err) {
          console.error('Hover provider error:', err);
          return null;
        }
      }
    });
  };

  // === Handlers ===
  const openProject = (project) => {
    setCurrentProject(project);
    setView('project-detail');
    setSelectedFile(null);
    setGraphElements(null);
    setFileContent('');
    setSearchResults([]);
    setSelectedSymbolId(null);
  };

  const handleBack = () => {
    setView('project-list');
    setCurrentProject(null);
  };

  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // Setup Monaco Providers
    setupMonacoProviders(editor, monaco);

    // Add click listener to detect symbol selection
    editor.onDidChangeCursorPosition(async (e) => {
      const position = e.position;
      const word = editor.getModel().getWordAtPosition(position);

      if (word) {
        try {
          const results = await axios.get(`${API_BASE}/search`, {
            params: { q: word.word, project_id: currentProject.id, limit: 1 }
          });

          if (results.data.length > 0) {
            setSelectedSymbolId(results.data[0].id);
          }
        } catch (err) {
          // Silently fail
        }
      }
    });
  };

  const handleCy = (cy) => {
    cyRef.current = cy;

    // Single click - show context
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      const symbolId = parseInt(node.id());
      setSelectedSymbolId(symbolId);

      const line = node.data('line');
      if (line && editorRef.current) {
        editorRef.current.revealLineInCenter(line);
        editorRef.current.setPosition({ lineNumber: line, column: 1 });
        editorRef.current.focus();
      }
    });

    // Double click - expand node (cross-file graph)
    cy.on('dbltap', 'node', async (evt) => {
      const node = evt.target;
      const symbolId = parseInt(node.id());

      try {
        message.loading('Loading cross-file relationships...', 0.5);
        const res = await axios.get(`${API_BASE}/graph/cross_file`, {
          params: {
            project_id: currentProject.id,
            symbol_id: symbolId,
            depth: 2
          }
        });

        if (res.data.elements && res.data.elements.nodes.length > 0) {
          setGraphElements(CytoscapeComponent.normalizeElements(res.data.elements));
        }
      } catch (err) {
        message.error('Failed to load cross-file graph');
      }
    });

    // Edge click
    cy.on('tap', 'edge', (evt) => {
      const edge = evt.target;
      const line = edge.data('line');
      if (line && editorRef.current) {
        editorRef.current.revealLineInCenter(line);
        editorRef.current.setPosition({ lineNumber: line, column: 1 });
        editorRef.current.focus();
      }
    });
  };

  const showDSM = () => {
    setIsDSMVisible(true);
    fetchDSM();
  };

  const onTreeSelect = (keys, info) => {
    if (info.node.isLeaf) {
      setSelectedFile(info.node.data);
    }
  };

  const handleNavigateToFile = (fileId, line) => {
    const file = files.find(f => f.id === fileId);
    if (file) {
      setSelectedFile(file);
      pendingJumpRef.current = line;
    }
  };

  // === Renderers (将在下一部分继续) ===

  const renderProjectList = () => (
    <div style={{ padding: '50px', maxWidth: '1000px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
        <Title level={2}>Projects</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)}>
          New Project
        </Button>
      </div>
      <Table
        dataSource={projects}
        rowKey="id"
        loading={loadingProjects}
        columns={[
          { title: 'Name', dataIndex: 'name', key: 'name', render: text => <b>{text}</b> },
          { title: 'Path', dataIndex: 'root_path', key: 'path' },
          { title: 'Created', dataIndex: 'created_at', key: 'created', render: t => new Date(t).toLocaleDateString() },
          {
            title: 'Action',
            key: 'action',
            render: (_, record) => (
              <Button type="link" onClick={() => openProject(record)}>Open</Button>
            )
          }
        ]}
      />
      <Modal
        title="Create New Project"
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={createProject}>
          <Form.Item name="name" label="Project Name" rules={[{ required: true }]}>
            <Input placeholder="My C Project" />
          </Form.Item>
          <Form.Item name="root_path" label="Root Path" rules={[{ required: true }]}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Input
                placeholder="E:\workspace\linux-kernel\drivers"
                value={rootPathInput}
                onChange={(e) => {
                  setRootPathInput(e.target.value);
                  form.setFieldsValue({ root_path: e.target.value });
                }}
              />
              <Button onClick={handleBrowseDirectory}>Browse</Button>
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );

  const renderDSM = () => {
    if (loadingDSM || !dsmData) return <Spin />;
    const { files, matrix } = dsmData;
    return (
      <div style={{ overflow: 'auto', maxHeight: '600px' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: '10px' }}>
          <thead>
            <tr>
              <th></th>
              {files.map((f, i) => (
                <th key={f.id} style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', padding: '5px', border: '1px solid #ddd' }}>{f.name} ({i + 1})</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {files.map((f, i) => (
              <tr key={f.id}>
                <td style={{ padding: '5px', border: '1px solid #ddd', fontWeight: 'bold' }}>{i + 1}. {f.name}</td>
                {matrix[i].map((val, j) => {
                  const isDiagonal = i === j;
                  const hasLoop = !isDiagonal && val > 0 && matrix[j][i] > 0;
                  let bg = 'white';
                  if (isDiagonal) bg = '#f0f0f0';
                  else if (hasLoop) bg = '#ffcccc';
                  else if (val > 0) bg = '#e6f7ff';
                  return <td key={j} style={{ width: 30, height: 30, textAlign: 'center', border: '1px solid #eee', backgroundColor: bg, color: val > 0 ? '#000' : '#ccc' }}>{val > 0 ? val : '.'}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderProjectDetail = () => (
    <Layout style={{ height: 'calc(100vh - 64px)' }}>
      <Sider width={300} theme="light" style={{ borderRight: '1px solid #f0f0f0', display: 'flex', flexDirection: 'column' }}>
        <Tabs 
            activeKey={sidebarMode} 
            onChange={setSidebarMode}
            type="card"
            size="small"
            style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
            tabBarStyle={{ margin: 0, padding: '4px 4px 0 4px', background: '#f5f5f5' }}
            items={[
                {
                    key: 'files',
                    label: 'Files',
                    children: (
                        <div style={{ height: 'calc(100vh - 110px)', display: 'flex', flexDirection: 'column' }}>
                            <div style={{ padding: '8px', borderBottom: '1px solid #f0f0f0', display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                                <Tooltip title="Rescan Project"><Button size="small" icon={<ReloadOutlined />} onClick={() => triggerScan(currentProject.id)} /></Tooltip>
                                <Tooltip title="DSM Matrix"><Button size="small" icon={<AppstoreOutlined />} onClick={showDSM} /></Tooltip>
                                <Tooltip title="Git History"><Button size="small" icon={<BranchesOutlined />} onClick={() => setShowGitPanel(true)} /></Tooltip>
                                <Tooltip title="Architecture"><Button size="small" icon={<ApartmentOutlined />} onClick={() => setShowArchPanel(true)} /></Tooltip>
                            </div>
                            <div ref={treeContainerRef} style={{ flex: 1, overflow: 'auto' }}>
                                {loadingFiles ? <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div> : (
                                <DirectoryTree
                                    multiple
                                    onSelect={onTreeSelect}
                                    treeData={treeData}
                                    selectedKeys={selectedFile ? [`file-${selectedFile.id}`] : []}
                                    style={{ background: 'transparent' }}
                                />
                                )}
                            </div>
                        </div>
                    )
                },
                {
                    key: 'structure',
                    label: 'Structure',
                    children: (
                         <div style={{ height: 'calc(100vh - 110px)', overflow: 'hidden' }}>
                            <StructurePanel 
                                fileId={selectedFile?.id} 
                                onSymbolSelect={(symbol) => {
                                    handleNavigateToFile(symbol.file_id || selectedFile.id, symbol.line);
                                    setSelectedSymbolId(symbol.id);
                                }} 
                            />
                        </div>
                    )
                }
            ]}
        />
      </Sider>

      <Content style={{ display: 'flex', flexDirection: 'row' }}>
        {/* Main Content Area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          {selectedFile ? (
            <>
              <div style={{ height: '40px', padding: '0 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #ddd', background: '#f5f5f5' }}>
                <Text strong>{selectedFile.path.split(/[/\\]/).pop()}</Text>
                <div>
                   {selectedSymbolId && <Tag color="blue">Selected Symbol ID: {selectedSymbolId}</Tag>}
                </div>
              </div>

              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: 'calc(100% - 40px)' }}>
                {/* Editor (100%) */}
                <div style={{ height: '100%', position: 'relative' }}>
                  {loadingContent ? (
                    <div style={{ height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                      <Spin size="large" tip="Loading file..." />
                    </div>
                  ) : (
                    <Editor
                      height="100%"
                      language="c"
                      theme="vs-light"
                      value={fileContent}
                      onMount={handleEditorDidMount}
                      options={{
                        readOnly: true,
                        minimap: { enabled: true },
                        scrollBeyondLastLine: false,
                        fontSize: 14,
                        lineNumbers: 'on'
                      }}
                    />
                  )}
                </div>
              </div>
            </>
          ) : (
            <Empty description="Select a file to view" style={{ marginTop: 100 }} />
          )}
        </div>

        {/* Right Panel: Context & Relations */}
        {selectedFile && (
          <div style={{ width: '400px', borderLeft: '1px solid #f0f0f0', display: 'flex', flexDirection: 'column', background: '#fff' }}>
            <Tabs 
                defaultActiveKey="context" 
                type="card"
                size="small"
                style={{ height: '100%' }}
                tabBarStyle={{ margin: 0, background: '#f5f5f5', padding: '4px 4px 0 4px' }}
                items={[
                    {
                        key: 'context',
                        label: 'Context Info',
                        children: (
                            <div style={{ height: '100%', overflow: 'auto' }}>
                                <ContextPanel
                                    symbolId={selectedSymbolId}
                                    onNavigate={handleNavigateToFile}
                                />
                            </div>
                        )
                    },
                    {
                        key: 'relations',
                        label: 'Relation Graph',
                        children: (
                            <div style={{ height: 'calc(100vh - 110px)', position: 'relative' }}>
                                <RelationGraph 
                                    projectId={currentProject.id}
                                    symbolId={selectedSymbolId}
                                    onNodeClick={(id, line, file) => {
                                        const targetFile = files.find(f => f.path.endsWith(file));
                                        if (targetFile) {
                                            if (targetFile.id !== selectedFile.id) {
                                                setSelectedFile(targetFile);
                                            }
                                        }
                                        pendingJumpRef.current = line;
                                        setSelectedSymbolId(parseInt(id));
                                    }}
                                />
                            </div>
                        )
                    }
                ]}
            />
          </div>
        )}
      </Content>

      {/* Modals and Drawers */}
      <Modal
        title="Dependency Structure Matrix (DSM)"
        open={isDSMVisible}
        onCancel={() => setIsDSMVisible(false)}
        footer={null}
        width={1200}
      >
        {renderDSM()}
      </Modal>

      <ScanProgress
        projectId={currentProject?.id}
        visible={showScanProgress}
        onComplete={(success) => {
          setShowScanProgress(false);
          if (success && currentProject) {
            fetchFiles(currentProject.id);
          }
        }}
      />

      <GitPanel
        projectId={currentProject?.id}
        currentFile={selectedFile}
        visible={showGitPanel}
        onClose={() => setShowGitPanel(false)}
      />

      <ArchitecturePanel
        projectId={currentProject?.id}
        visible={showArchPanel}
        onClose={() => setShowArchPanel(false)}
        onFileSelect={(fileId) => {
          const file = files.find(f => f.id === fileId);
          if (file) setSelectedFile(file);
          setShowArchPanel(false);
        }}
      />
    </Layout>
  );

  // === Main Render ===
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#001529', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {view === 'project-detail' && (
            <Button type="link" icon={<ArrowLeftOutlined />} onClick={handleBack} style={{ color: 'white' }}>
              Back
            </Button>
          )}
          <Title level={3} style={{ color: 'white', margin: 0 }}>
            <RocketOutlined /> CodeUnderstand
          </Title>
          {currentProject && (
            <Tag color="blue">{currentProject.name}</Tag>
          )}
        </div>

        {view === 'project-detail' && (
          <AutoComplete
            style={{ width: 400 }}
            options={searchResults}
            onSearch={handleSearch}
            onSelect={onSelectSymbol}
            placeholder="Search symbols (Ctrl+P)"
          >
            <Input prefix={<SearchOutlined />} />
          </AutoComplete>
        )}
      </Header>

      <Content>
        {view === 'project-list' && renderProjectList()}
        {view === 'project-detail' && renderProjectDetail()}
      </Content>
    </Layout>
  );
};

export default App;
