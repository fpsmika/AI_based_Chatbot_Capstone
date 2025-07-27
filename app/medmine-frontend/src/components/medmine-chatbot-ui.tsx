import React, { useState, useRef, useEffect } from 'react';
import type { CSSProperties } from 'react';

const Icons = {
  Send: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m22 2-7 20-4-9-9-4Z"/>
      <path d="M22 2 11 13"/>
    </svg>
  ),
  Upload: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7,10 12,5 17,10"/>
      <line x1="12" y1="5" x2="12" y2="15"/>
    </svg>
  ),
  FileSpreadsheet: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14,2 14,8 20,8"/>
      <path d="M8 13h2"/>
      <path d="M14 13h2"/>
      <path d="M8 17h2"/>
      <path d="M14 17h2"/>
    </svg>
  ),
  Download: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7,10 12,15 17,10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  ),
  Settings: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3"/>
      <path d="M12 1v6m0 6v6"/>
      <path d="m21 12-6-6v12l6-6z"/>
    </svg>
  ),
  Search: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="8"/>
      <path d="m21 21-4.35-4.35"/>
    </svg>
  ),
  User: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>
  ),
  Bot: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 8V4H8"/>
      <rect width="16" height="12" x="4" y="8" rx="2"/>
      <path d="M2 14h2"/>
      <path d="M20 14h2"/>
      <path d="M15 13v2"/>
      <path d="M9 13v2"/>
    </svg>
  ),
  Loader: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  ),
  X: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 6 6 18"/>
      <path d="m6 6 12 12"/>
    </svg>
  ),
  Database: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <ellipse cx="12" cy="5" rx="9" ry="3"/>
      <path d="M3 5v14c0 3 6 3 9 3s9 0 9-3V5"/>
      <path d="M3 12c0 3 6 3 9 3s9 0 9-3"/>
    </svg>
  )
};

// Enhanced interfaces
interface Message {
  id: number;
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  context?: string;
  suggestions?: string[];
  sources?: Array<{
    source: string;
    ItemDesc?: string;
    Vendor?: string;
    TotalSpend?: number;
    similarity?: number;
    [key: string]: any;
  }>;
}

interface SearchResult {
  "@search.score"?: number;
  id: string;
  content?: string;
  TransactionID: string;
  ItemDesc: string;
  Manufacturer?: string;
  Vendor: string;
  FacilityType?: string;
  Region?: string;
  PricePaid?: number;
  TotalSpend: number;
  LoadDate?: string;
  metadata?: string;
  similarity?: number;
  [key: string]: any;
}

interface ChatResponse {
  response: string;
  suggestions: string[];
  context?: string;
  session_id?: string;
  sources?: Array<{
    source: string;
    ItemDesc?: string;
    Vendor?: string;
    TotalSpend?: number;
    similarity?: number;
    [key: string]: any;
  }>;
}

const API_BASE = 'http://localhost:8000/api/v1';

const MedMineChatbot = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      type: 'assistant',
      content: "Hello! I'm Earl, your AI assistant for purchase order data analysis. Upload a file or ask me about your procurement data.",
      timestamp: new Date()
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [fileData, setFileData] = useState<Array<Record<string, string>> | null>(null);
  const [showFilePreview, setShowFilePreview] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [currentBatch, setCurrentBatch] = useState<string | null>(null);
  const [totalRows, setTotalRows] = useState<number>(0);

  const [sessionId] = useState(() => {
    return crypto.randomUUID();
  });

  const querySuggestions = [
    "What's our total spending on gloves this year?",
    "Compare vendor A and vendor B for IV bags",
    "Which department purchased the most items?",
    "Show me the top 5 most expensive purchases",
    "How has our PPE spending changed over time?",
    "/search surgical gloves"
  ];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate extension client‑side
    const allowed = ['.csv', '.xlsx', '.xls'];
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowed.includes(ext)) {
      setMessages(m => [
        ...m,
        {
          id: Date.now(),
          type: 'system',
          content: `Unsupported file type "${ext}". Please upload one of: ${allowed.join(', ')}`,
          timestamp: new Date()
        }
      ]);
      return;
    }

    setUploadedFile(file);
    setMessages(m => [
      ...m,
      {
        id: Date.now(),
        type: 'system',
        content: `Uploading "${file.name}"…`,
        timestamp: new Date()
      }
    ]);

    try {
      // 1) Send file to /process → returns batch_id with status="enqueued"
      const fd = new FormData();
      fd.append('file', file);

      const res = await fetch(`${API_BASE}/process`, {
        method: 'POST',
        body: fd
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const json = await res.json();

      // accept both 'success' (old flow) or 'enqueued' (new background flow)
      if (json.status !== 'success' && json.status !== 'enqueued') {
        throw new Error(json.detail || 'Server processing failed');
      }

      const { batch_id, rows_loaded } = json;

      // 2) Notify user
      setMessages(m => {
        const withoutUploading = m.slice(0, -1);
        const verb = json.status === 'success' ? 'Processed' : 'Enqueued';
        return [
          ...withoutUploading,
          {
            id: Date.now(),
            type: 'system',
            content: `✅ ${verb} batch ${batch_id}: ${rows_loaded} rows.`,
            timestamp: new Date()
          }
        ];
      });

      setCurrentBatch(batch_id);
      setTotalRows(rows_loaded);

      // 3) Fetch first page of data (may be empty initially—poll or let user refresh)
      const pageRes = await fetch(
        `${API_BASE}/cosmos/data/${batch_id}?offset=0&limit=100`
      );
      if (!pageRes.ok) throw new Error(`Paging fetch failed: ${pageRes.statusText}`);
      const pageData: any[] = await pageRes.json();

      setFileData(pageData);
      setShowFilePreview(true);

    } catch (err) {
      console.error(err);
      setMessages(m => {
        const withoutUploading = m.slice(0, -1);
        return [
          ...withoutUploading,
          {
            id: Date.now(),
            type: 'system',
            content: `❌ Failed to process "${file.name}": ${err instanceof Error ? err.message : err}`,
            timestamp: new Date()
          }
        ];
      });
      setUploadedFile(null);
      setFileData(null);
      setShowFilePreview(false);
    }
  };

  // New vector search functionality
  const handleVectorSearch = async (query: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/search/vector-search?q=${encodeURIComponent(query)}&top_k=10`
      );
      
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      
      const results: SearchResult[] = await response.json();
      setSearchResults(results);
      setShowSearchResults(true);
      
      setMessages(m => [
        ...m,
        {
          id: Date.now(),
          type: 'system',
          content: `Found ${results.length} relevant items matching "${query}"`,
          timestamp: new Date(),
          sources: results.map(r => ({
            source: 'azure_search',
            ItemDesc: r.ItemDesc,
            Vendor: r.Vendor,
            TotalSpend: r.TotalSpend,
            similarity: r.similarity || r["@search.score"]
          }))
        }
      ]);
      
    } catch (err) {
      console.error("Search error:", err);
      setMessages(m => [
        ...m,
        {
          id: Date.now(),
          type: 'system',
          content: `Search failed: ${err instanceof Error ? err.message : String(err)}`,
          timestamp: new Date()
        }
      ]);
    }
  };

  async function fetchBatchData(batchId: string, offset = 0, limit = 100) {
    const res = await fetch(
      `${API_BASE}/cosmos/data/${batchId}?offset=${offset}&limit=${limit}`
    );
    if (!res.ok) {
      console.error("Fetch error:", res.statusText);
      return [];
    }
    return (await res.json()) as any[];
  }

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    // 1️⃣ Add the user's message to chat
    const userMsg: Message = {
      id: Date.now(),
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    
    const currentInput = inputValue;
    setInputValue('');
    setIsLoading(true);

    // Check for special commands
    if (currentInput.startsWith("/search ")) {
      const query = currentInput.substring(8).trim();
      await handleVectorSearch(query);
      setIsLoading(false);
      return;
    }

    try {
      // 2️⃣ Build payload (with optional CSV)
      const payload = {
        message: currentInput,
        session_id: sessionId,
        csv_data: fileData && fileData.length > 0
          ? {
              filename: uploadedFile?.name || 'uploaded_file.csv',
              headers: Object.keys(fileData[0]).filter(k => k !== 'id'),
              data: fileData.map(({ id, ...rest }) => rest),
              row_count: fileData.length,
            }
          : null,
      };

      // 3️⃣ Call your chat endpoint
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const { response: aiText, suggestions, context, sources }: ChatResponse = await response.json();

      // 4️⃣ Build the assistant's message
      const aiMsg: Message = {
        id: Date.now() + 1,
        type: 'assistant',
        content: aiText,
        timestamp: new Date(),
        context,
        suggestions: suggestions || [],
        sources
      };

      setMessages(prev => [...prev, aiMsg]);
    } catch (err) {
      console.error('Chat API Error:', err);
      const errorMessage = err instanceof Error ? err.message : String(err);
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + 1,
          type: 'assistant',
          content: `⚠️ Error: ${errorMessage}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setInputValue(suggestion);
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const styles: Record<string, CSSProperties> = {
    container: {
      display: 'flex',
      height: '100vh',
      backgroundColor: '#f9fafb',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    },
    sidebar: {
      width: '320px',
      backgroundColor: 'white',
      borderRight: '1px solid #e5e7eb',
      display: 'flex',
      flexDirection: 'column'
    },
    header: {
      padding: '24px',
      borderBottom: '1px solid #e5e7eb'
    },
    headerContent: {
      display: 'flex',
      alignItems: 'center',
      gap: '12px'
    },
    logo: {
      width: '40px',
      height: '40px',
      backgroundColor: '#2563eb',
      borderRadius: '8px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'white'
    },
    title: {
      fontSize: '20px',
      fontWeight: 'bold',
      color: '#111827',
      margin: 0
    },
    subtitle: {
      fontSize: '14px',
      color: '#6b7280',
      margin: 0
    },
    uploadSection: {
      padding: '16px',
      borderBottom: '1px solid #e5e7eb'
    },
    uploadTitle: {
      fontWeight: '500',
      color: '#111827',
      marginBottom: '12px',
      fontSize: '14px'
    },
    uploadButton: {
      width: '100%',
      padding: '12px',
      border: '2px dashed #d1d5db',
      borderRadius: '8px',
      backgroundColor: 'transparent',
      cursor: 'pointer',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '8px',
      transition: 'border-color 0.2s',
      color: '#6b7280'
    },
    uploadButtonHover: {
      borderColor: '#60a5fa'
    },
    fileInfo: {
      marginTop: '12px',
      padding: '12px',
      backgroundColor: '#dcfce7',
      borderRadius: '8px'
    },
    fileInfoContent: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
    },
    fileInfoText: {
      fontSize: '14px',
      color: '#166534'
    },
    previewButton: {
      fontSize: '12px',
      color: '#2563eb',
      textDecoration: 'underline',
      backgroundColor: 'transparent',
      border: 'none',
      cursor: 'pointer',
      marginTop: '4px'
    },
    refreshButton: {
      marginTop: '8px',
      padding: '8px 12px',
      backgroundColor: '#2563eb',
      color: 'white',
      border: 'none',
      borderRadius: '6px',
      cursor: 'pointer',
      fontSize: '12px'
    },
    previewSection: {
      padding: '16px',
      borderBottom: '1px solid #e5e7eb',
      maxHeight: '256px',
      overflowY: 'auto'
    },
    previewHeader: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: '8px'
    },
    previewTitle: {
      fontWeight: '500',
      color: '#111827',
      fontSize: '14px'
    },
    closeButton: {
      backgroundColor: 'transparent',
      border: 'none',
      color: '#6b7280',
      cursor: 'pointer',
      padding: '4px'
    },
    previewTable: {
      fontSize: '12px',
      backgroundColor: '#f9fafb',
      borderRadius: '4px',
      padding: '8px',
      overflowX: 'auto'
    },
    table: {
      width: '100%',
      borderCollapse: 'collapse'
    },
    th: {
      textAlign: 'left',
      padding: '4px',
      borderBottom: '1px solid #e5e7eb',
      color: '#111827',
    },
    td: {
      padding: '4px',
      borderBottom: '1px solid #f3f4f6',
      color: '#111827',
    },
    suggestionsSection: {
      padding: '16px',
      flex: 1
    },
    suggestionsTitle: {
      fontWeight: '500',
      color: '#111827',
      marginBottom: '12px',
      fontSize: '14px'
    },
    suggestion: {
      width: '100%',
      textAlign: 'left',
      padding: '8px',
      fontSize: '14px',
      color: '#6b7280',
      backgroundColor: 'transparent',
      border: 'none',
      borderRadius: '8px',
      cursor: 'pointer',
      marginBottom: '8px',
      transition: 'background-color 0.2s'
    },
    suggestionHover: {
      backgroundColor: '#f3f4f6'
    },
    searchCommands: {
      marginTop: '16px',
      padding: '12px',
      backgroundColor: '#f3f4f6',
      borderRadius: '8px'
    },
    searchCommandsTitle: {
      fontWeight: '500',
      color: '#111827',
      marginBottom: '8px',
      fontSize: '14px'
    },
    searchCommandsText: {
      fontSize: '12px',
      color: '#6b7280',
      lineHeight: '1.4'
    },
    codeSpan: {
      backgroundColor: 'white',
      padding: '2px 4px',
      borderRadius: '4px',
      fontFamily: 'monospace'
    },
    mainArea: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column'
    },
    chatHeader: {
      backgroundColor: 'white',
      borderBottom: '1px solid #e5e7eb',
      padding: '16px'
    },
    chatHeaderContent: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    },
    chatTitle: {
      fontSize: '18px',
      fontWeight: '600',
      color: '#111827',
      margin: 0
    },
    chatSubtitle: {
      fontSize: '14px',
      color: '#6b7280',
      margin: 0
    },
    chatActions: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
    },
    actionButton: {
      padding: '8px',
      color: '#6b7280',
      backgroundColor: 'transparent',
      border: 'none',
      borderRadius: '8px',
      cursor: 'pointer',
      transition: 'all 0.2s'
    },
    actionButtonHover: {
      color: '#374151',
      backgroundColor: '#f3f4f6'
    },
    messagesArea: {
      flex: 1,
      overflowY: 'auto',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px'
    },
    message: {
      display: 'flex',
      width: '100%'
    },
    messageUser: {
      justifyContent: 'flex-end'
    },
    messageAssistant: {
      justifyContent: 'flex-start'
    },
    messageContent: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '12px'
    },
    messageContentReverse: {
      flexDirection: 'row-reverse'
    },
    avatar: {
      width: '32px',
      height: '32px',
      borderRadius: '50%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'white'
    },
    avatarUser: {
      backgroundColor: '#2563eb'
    },
    avatarAssistant: {
      backgroundColor: '#6b7280'
    },
    avatarSystem: {
      backgroundColor: '#059669'
    },
    bubble: {
      padding: '12px 16px',
      borderRadius: '12px',
      maxWidth: '65%',
      wordBreak: 'break-word'
    },
    bubbleUser: {
      backgroundColor: '#2563eb',
      color: 'white'
    },
    bubbleAssistant: {
      backgroundColor: '#f3f4f6',
      color: '#111827'
    },
    bubbleSystem: {
      backgroundColor: '#dcfce7',
      color: '#166534'
    },
    messageText: {
      fontSize: '14px',
      lineHeight: '1.5',
      margin: 0
    },
    timestamp: {
      fontSize: '12px',
      marginTop: '4px',
      opacity: 0.7
    },
    suggestionBubble: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px',
      marginTop: '8px'
    },
    suggestionChip: {
      padding: '4px 8px',
      fontSize: '12px',
      backgroundColor: '#e0f2fe',
      color: '#0277bd',
      border: 'none',
      borderRadius: '12px',
      cursor: 'pointer',
      transition: 'background-color 0.2s'
    },
    suggestionChipHover: {
      backgroundColor: '#b3e5fc'
    },
    sourcesSection: {
      marginTop: '8px',
      padding: '8px',
      backgroundColor: '#f9fafb',
      borderRadius: '8px',
      borderLeft: '3px solid #2563eb'
    },
    sourcesTitle: {
      fontSize: '12px',
      fontWeight: '500',
      color: '#374151',
      marginBottom: '4px'
    },
    sourceItem: {
      fontSize: '11px',
      color: '#6b7280',
      marginBottom: '2px'
    },
    loadingMessage: {
      display: 'flex',
      justifyContent: 'flex-start'
    },
    loadingContent: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '12px'
    },
    loadingBubble: {
      padding: '12px 16px',
      borderRadius: '12px',
      backgroundColor: '#f3f4f6'
    },
    loadingText: {
      display: 'flex',
      alignItems: 'center',
      gap: '8px'
    },
    spinner: {
      animation: 'spin 1s linear infinite'
    },
    inputArea: {
      backgroundColor: 'white',
      borderTop: '1px solid #e5e7eb',
      padding: '16px'
    },
    inputContainer: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: '12px'
    },
    inputWrapper: {
      flex: 1
    },
    textarea: {
      width: '100%',
      padding: '12px',
      border: '1px solid #d1d5db',
      borderRadius: '8px',
      resize: 'none',
      fontSize: '14px',
      fontFamily: 'inherit',
      outline: 'none',
      transition: 'border-color 0.2s',
      boxSizing: 'border-box'
    },
    textareaFocus: {
      borderColor: '#2563eb',
      boxShadow: '0 0 0 3px rgba(37, 99, 235, 0.1)'
    },
    sendButton: {
      padding: '12px 24px',
      backgroundColor: '#2563eb',
      color: 'white',
      border: 'none',
      borderRadius: '8px',
      cursor: 'pointer',
      fontSize: '14px',
      fontWeight: '500',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      transition: 'background-color 0.2s'
    },
    sendButtonHover: {
      backgroundColor: '#1d4ed8'
    },
    sendButtonDisabled: {
      opacity: 0.5,
      cursor: 'not-allowed'
    },
    disclaimer: {
      fontSize: '12px',
      color: '#6b7280',
      marginTop: '8px',
      textAlign: 'center'
    },
    searchResultsPanel: {
      position: 'fixed',
      bottom: '100px',
      right: '24px',
      width: '384px',
      maxHeight: '384px',
      overflowY: 'auto',
      backgroundColor: 'white',
      border: '1px solid #e5e7eb',
      borderRadius: '12px',
      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
      zIndex: 50
    },
    searchResultsHeader: {
      padding: '16px',
      borderBottom: '1px solid #e5e7eb',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    },
    searchResultsTitle: {
      fontWeight: '600',
      color: '#111827',
      fontSize: '16px'
    },
    searchResultsContent: {
      padding: '16px'
    },
    searchResultItem: {
      padding: '12px',
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      marginBottom: '12px',
      cursor: 'pointer',
      transition: 'background-color 0.2s'
    },
    searchResultItemHover: {
      backgroundColor: '#f9fafb'
    },
    searchResultItemDesc: {
      fontWeight: '500',
      fontSize: '14px',
      color: '#111827',
      marginBottom: '4px'
    },
    searchResultItemDetail: {
      fontSize: '14px',
      color: '#6b7280',
      marginBottom: '2px'
    },
    searchResultScore: {
      fontSize: '12px',
      color: '#9ca3af'
    }
  };

  return (
    <div style={styles.container}>
      {/* Sidebar */}
      <div style={styles.sidebar}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerContent}>
            <div style={styles.logo}>
              <Icons.Bot />
            </div>
            <div>
              <h1 style={styles.title}>Earl</h1>
              <p style={styles.subtitle}>MedMine AI Assistant</p>
            </div>
          </div>
        </div>

        {/* Upload Area */}
        <div style={styles.uploadSection}>
          <h3 style={styles.uploadTitle}>Data Upload</h3>
          <button
            onClick={() => fileInputRef.current?.click()}
            style={styles.uploadButton}
            onMouseEnter={(e) => (e.target as HTMLButtonElement).style.borderColor = '#60a5fa'}
            onMouseLeave={(e) => (e.target as HTMLButtonElement).style.borderColor = '#d1d5db'}
          >
            <Icons.Upload />
            <span style={{fontSize: '14px'}}>Upload CSV/Excel</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFileUpload}
            style={{display: 'none'}}
          />
          
          {uploadedFile && (
            <div style={styles.fileInfo}>
              <div style={styles.fileInfoContent}>
                <Icons.FileSpreadsheet />
                <span style={styles.fileInfoText}>{uploadedFile.name}</span>
              </div>
              <button
                onClick={() => setShowFilePreview(!showFilePreview)}
                style={styles.previewButton}
              >
                {showFilePreview ? 'Hide' : 'Show'} Preview
              </button>
              
              {uploadedFile && currentBatch && (
                <button
                  onClick={async () => {
                    const data = await fetchBatchData(currentBatch);
                    console.log("🔄 refreshed data:", data);
                    setFileData(data);
                    setShowFilePreview(true);
                  }}
                  style={styles.refreshButton}
                >
                  Refresh Data from Cosmos
                </button>
              )}
            </div>
          )}
        </div>

        {/* Preview Section */}
        {showFilePreview && fileData && (
          <div style={styles.previewSection}>
            <div style={styles.previewHeader}>
              <h4 style={styles.previewTitle}>Data Preview</h4>
              <button
                onClick={() => setShowFilePreview(false)}
                style={styles.closeButton}
              >
                <Icons.X />
              </button>
            </div>
            <div style={styles.previewTable}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    {fileData && fileData.length > 0 && Object.keys(fileData[0])
                      .filter(key => key !== 'id')
                      .slice(0, 4) // Show first 4 columns
                      .map((key) => (
                        <th key={key} style={styles.th}>
                          {key.charAt(0).toUpperCase() + key.slice(1)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {fileData?.slice(0, 3).map((row, index) => (
                      <tr key={row.id || index}>
                        {Object.keys(row)
                          .filter(key => key !== 'id')
                          .slice(0, 4)
                          .map((key) => (
                            <td key={key} style={styles.td}>
                              {row[key]}
                            </td>
                         ))}
                        </tr>
                      ))}
                  </tbody>
              </table>
              {fileData.length > 3 && (
                <p style={{color: '#6b7280', marginTop: '4px', fontSize: '12px'}}>
                  +{fileData.length - 3} more rows
                </p>
              )}
            </div>
          </div>
        )}

        {/* Suggestions Section */}
        <div style={styles.suggestionsSection}>
          <h3 style={styles.suggestionsTitle}>Quick Questions</h3>
          <div>
            {querySuggestions.map((suggestion, index) => (
              <button
                key={index}
                onClick={() => handleSuggestionClick(suggestion)}
                style={styles.suggestion}
                onMouseEnter={(e) => {
                  (e.target as HTMLButtonElement).style.backgroundColor = '#f3f4f6';
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLButtonElement).style.backgroundColor = 'transparent';
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
          
          {/* Search Commands Info */}
          <div style={styles.searchCommands}>
            <h4 style={styles.searchCommandsTitle}>Search Commands</h4>
            <div style={styles.searchCommandsText}>
              <p><span style={styles.codeSpan}>/search [query]</span> - Vector search</p>
              <p>Example: <span style={styles.codeSpan}>/search gloves</span></p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div style={styles.mainArea}>
        {/* Chat Header */}
        <div style={styles.chatHeader}>
          <div style={styles.chatHeaderContent}>
            <div>
              <h2 style={styles.chatTitle}>Purchase Order Analysis</h2>
              <p style={styles.chatSubtitle}>Ask Earl about your procurement data</p>
            </div>
            <div style={styles.chatActions}>
              <button
                onClick={() => setShowSearchResults(!showSearchResults)}
                style={styles.actionButton}
                onMouseEnter={(e) => {
                  (e.target as HTMLButtonElement).style.color = '#374151';
                  (e.target as HTMLButtonElement).style.backgroundColor = '#f3f4f6';
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLButtonElement).style.color = '#6b7280';
                  (e.target as HTMLButtonElement).style.backgroundColor = 'transparent';
                }}
              >
                <Icons.Search />
              </button>
              <button
                style={styles.actionButton}
                onMouseEnter={(e) => {
                  (e.target as HTMLButtonElement).style.color = '#374151';
                  (e.target as HTMLButtonElement).style.backgroundColor = '#f3f4f6';
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLButtonElement).style.color = '#6b7280';
                  (e.target as HTMLButtonElement).style.backgroundColor = 'transparent';
                }}
              >
                <Icons.Download />
              </button>
              <button
                style={styles.actionButton}
                onMouseEnter={(e) => {
                  (e.target as HTMLButtonElement).style.color = '#374151';
                  (e.target as HTMLButtonElement).style.backgroundColor = '#f3f4f6';
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLButtonElement).style.color = '#6b7280';
                  (e.target as HTMLButtonElement).style.backgroundColor = 'transparent';
                }}
              >
                <Icons.Settings />
              </button>
            </div>
          </div>
        </div>

        {/* Messages Area */}
        <div style={styles.messagesArea}>
          {messages.map((message) => (
            <div
              key={message.id}
              style={{
                ...styles.message,
                ...(message.type === 'user' ? styles.messageUser : styles.messageAssistant)
              }}
            >
              <div
                style={{
                  ...styles.messageContent,
                  ...(message.type === 'user' ? styles.messageContentReverse : {})
                }}
              >
                <div
                  style={{
                    ...styles.avatar,
                    ...(message.type === 'user' ? styles.avatarUser : 
                        message.type === 'system' ? styles.avatarSystem : styles.avatarAssistant)
                  }}
                >
                  {message.type === 'user' ? <Icons.User /> : 
                   message.type === 'system' ? <Icons.Database /> : <Icons.Bot />}
                </div>
                <div
                  style={{
                    ...styles.bubble,
                    ...(message.type === 'user' ? styles.bubbleUser :
                        message.type === 'system' ? styles.bubbleSystem : styles.bubbleAssistant)
                  }}
                >
                  <p style={styles.messageText}>{message.content}</p>
                  
                  {/* Suggestions */}
                  {message.suggestions && message.suggestions.length > 0 && (
                    <div style={styles.suggestionBubble}>
                      {message.suggestions.map((suggestion, index) => (
                        <button
                          key={index}
                          onClick={() => handleSuggestionClick(suggestion)}
                          style={styles.suggestionChip}
                          onMouseEnter={(e) => {
                            (e.target as HTMLButtonElement).style.backgroundColor = '#b3e5fc';
                          }}
                          onMouseLeave={(e) => {
                            (e.target as HTMLButtonElement).style.backgroundColor = '#e0f2fe';
                          }}
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                  
                  {/* Sources */}
                  {message.sources && message.sources.length > 0 && (
                    <div style={styles.sourcesSection}>
                      <p style={styles.sourcesTitle}>Sources:</p>
                      <div>
                        {message.sources.slice(0, 3).map((source, index) => (
                          <div key={index} style={styles.sourceItem}>
                            <span style={{fontWeight: '500'}}>{source.ItemDesc}</span>
                            {source.Vendor && <span> • {source.Vendor}</span>}
                            {source.TotalSpend && <span> • ${source.TotalSpend.toLocaleString()}</span>}
                            {source.similarity && <span> • Score: {source.similarity.toFixed(3)}</span>}
                          </div>
                        ))}
                        {message.sources.length > 3 && (
                          <div style={styles.sourceItem}>
                            +{message.sources.length - 3} more sources
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  <p style={styles.timestamp}>
                    {message.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div style={styles.loadingMessage}>
              <div style={styles.loadingContent}>
                <div style={{...styles.avatar, ...styles.avatarAssistant}}>
                  <Icons.Bot />
                </div>
                <div style={styles.loadingBubble}>
                  <div style={styles.loadingText}>
                    <div style={styles.spinner}>
                      <Icons.Loader />
                    </div>
                    <p style={{...styles.messageText, color: '#6b7280'}}>Earl is analyzing...</p>
                  </div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div style={styles.inputArea}>
          <div style={styles.inputContainer}>
            <div style={styles.inputWrapper}>
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask Earl about your purchase data or type /search to find specific items..."
                style={styles.textarea}
                rows={3}
                disabled={isLoading}
                onFocus={(e) => {
                  e.target.style.borderColor = '#2563eb';
                  e.target.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = '#d1d5db';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>
            <button
              onClick={handleSendMessage}
              disabled={isLoading || !inputValue.trim()}
              style={{
                ...styles.sendButton,
                ...(isLoading || !inputValue.trim() ? styles.sendButtonDisabled : {})
              }}
              onMouseEnter={(e) => {
                if (!(e.target as HTMLButtonElement).disabled) {
                  (e.target as HTMLButtonElement).style.backgroundColor = '#1d4ed8';
                }
              }}
              onMouseLeave={(e) => {
                if (!(e.target as HTMLButtonElement).disabled) {
                  (e.target as HTMLButtonElement).style.backgroundColor = '#2563eb';
                }
              }}
            >
              <span>Ask Earl</span>
              <Icons.Send />
            </button>
          </div>
          <p style={styles.disclaimer}>
            Earl can analyze your procurement data, compare vendors, and provide spending insights. Use /search for vector search.
          </p>
        </div>
      </div>

      {/* Search Results Panel */}
      {showSearchResults && searchResults.length > 0 && (
        <div style={styles.searchResultsPanel}>
          <div style={styles.searchResultsHeader}>
            <h3 style={styles.searchResultsTitle}>Search Results</h3>
            <button 
              onClick={() => setShowSearchResults(false)}
              style={styles.closeButton}
            >
              <Icons.X />
            </button>
          </div>
          <div style={styles.searchResultsContent}>
            {searchResults.slice(0, 10).map((result, index) => (
              <div 
                key={index} 
                style={styles.searchResultItem}
                onMouseEnter={(e) => {
                  (e.target as HTMLDivElement).style.backgroundColor = '#f9fafb';
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLDivElement).style.backgroundColor = 'white';
                }}
              >
                <div style={styles.searchResultItemDesc}>{result.ItemDesc}</div>
                <div style={styles.searchResultItemDetail}>Vendor: {result.Vendor}</div>
                <div style={styles.searchResultItemDetail}>Total: ${result.TotalSpend?.toLocaleString()}</div>
                <div style={styles.searchResultScore}>
                  Score: {(result.similarity || result["@search.score"] || 0).toFixed(3)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <style>
        {`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}
      </style>
    </div>
  );
};

export default MedMineChatbot;