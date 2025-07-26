import React, { useState, useRef, useEffect } from 'react';
import type { CSSProperties } from 'react';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';


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
  )
};

const MedMineChatbot = () => {
  const [messages, setMessages] = useState([
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

const [currentBatch, setCurrentBatch] = useState<string | null>(null);
const [totalRows,   setTotalRows]   = useState<number>(0);



  const querySuggestions = [
    "What's our total spending on gloves this year?",
    "Compare vendor A and vendor B for IV bags",
    "Which department purchased the most items?",
    "Show me the top 5 most expensive purchases",
    "How has our PPE spending changed over time?"
  ];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);


/*
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
  const file = event.target.files?.[0];
  if (file) {
    setUploadedFile(file);
    setShowFilePreview(true);

    // Helper function to process parsed data
    const processData = (headers: string[], rows: (string | number | null | undefined)[][]) => {
      const parsedData = rows
        .filter(row => row.length >= headers.length && row.some(cell => cell !== null && cell !== undefined && String(cell).trim()))
        .map((row, index) => {
          const item: Record<string, string> = { id: String(index + 1) };
          headers.forEach((header, i) => {
            const cleanHeader = String(header).trim().toLowerCase().replace(/\s+/g, '_');
            item[cleanHeader] = row[i] !== null && row[i] !== undefined ? String(row[i]).trim() : '';
          });
          return item;
        });
      
      setFileData(parsedData);
      
      const newMessage = {
        id: Date.now(),
        type: 'system',
        content: `File "${file.name}" uploaded successfully. ${parsedData.length} records loaded.`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, newMessage]);
    };
*/

const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
  console.log("🔥 handleFileUpload fired!", event.target.files);
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
        content: `Unsupported file type “${ext}”. Please upload one of: ${allowed.join(', ')}`,
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
      content: `Uploading “${file.name}”…`,
      timestamp: new Date()
    }
  ]);

  try {
    // 1) Send file to /process → returns batch_id with status="enqueued"
    const fd = new FormData();
    fd.append('file', file);

    const res = await fetch('http://localhost:8000/api/v1/process', {
      method: 'POST',
      body: fd
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const json = await res.json();
    console.log("✅ process response:", json);

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
      `http://localhost:8000/api/v1/cosmos/data/${batch_id}?offset=0&limit=100`
    );
    if (!pageRes.ok) throw new Error(`Paging fetch failed: ${pageRes.statusText}`);
    const pageData: any[] = await pageRes.json();
    console.log("⚙️ Retrieved pageData from Cosmos:", pageData);

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
          content: `❌ Failed to process “${file.name}”: ${err instanceof Error ? err.message : err}`,
          timestamp: new Date()
        }
      ];
    });
    setUploadedFile(null);
    setFileData(null);
    setShowFilePreview(false);
  }
};


/*
    // Parse CSV files
    if (file.type === 'text/csv' || file.name.endsWith('.csv')) {
      Papa.parse(file, {
        complete: (results) => {
          if (results.data && results.data.length > 0) {
            const headers = results.data[0] as string[];
            const rows = results.data.slice(1) as string[][];
            processData(headers, rows);
          }
        },
        header: false,
        skipEmptyLines: true,
        error: (error) => {
          console.error('CSV parsing error:', error);
          const errorMessage = {
            id: Date.now(),
            type: 'system',
            content: `Error parsing CSV file "${file.name}": ${error.message}`,
            timestamp: new Date()
          };
          setMessages(prev => [...prev, errorMessage]);
        }
      });
    } 
    // Parse Excel files (.xlsx, .xls)
    else if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = new Uint8Array(e.target?.result as ArrayBuffer);
          const workbook = XLSX.read(data, { type: 'array' });
          
          // Get the first worksheet
          const sheetName = workbook.SheetNames[0];
          const worksheet = workbook.Sheets[sheetName];
          
          // Convert to JSON array format
          const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 }) as (string | number | null | undefined)[][];
          
          if (jsonData.length > 0) {
            const headers = jsonData[0] as string[];
            const rows = jsonData.slice(1) as (string | number | null | undefined)[][];
            processData(headers, rows);
          } else {
            const errorMessage = {
              id: Date.now(),
              type: 'system',
              content: `Excel file "${file.name}" appears to be empty.`,
              timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
          }
        } catch (error) {
          console.error('Excel parsing error:', error);
          const errorMessage = {
            id: Date.now(),
            type: 'system',
            content: `Error parsing Excel file "${file.name}": ${error instanceof Error ? error.message : 'Unknown error'}`,
            timestamp: new Date()
          };
          setMessages(prev => [...prev, errorMessage]);
        }
      };
      
      reader.onerror = () => {
        const errorMessage = {
          id: Date.now(),
          type: 'system',
          content: `Error reading file "${file.name}".`,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, errorMessage]);
      };
      
      reader.readAsArrayBuffer(file);
    } 
    else {
      // Unsupported file type
      const errorMessage = {
        id: Date.now(),
        type: 'system',
        content: `File type not supported. Please upload a CSV or Excel (.xlsx, .xls) file.`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  }
};

*/
// Somewhere near the top of your component:
async function fetchBatchData(batchId: string, offset = 0, limit = 100) {
  const res = await fetch(
    `http://localhost:8000/api/v1/cosmos/data/${batchId}?offset=${offset}&limit=${limit}`
  );
  if (!res.ok) {
    console.error("Fetch error:", res.statusText);
    return [];
  }
  return (await res.json()) as any[];
}

// somewhere near the top of the component – use whichever store you prefer
const [sessionId] = useState(() => {
  // try to re-use a session across page reloads
  return localStorage.getItem('mmSession') ?? crypto.randomUUID();
});

useEffect(() => {
  localStorage.setItem('mmSession', sessionId);
}, [sessionId]);





interface ChatResult {
  response: string;
  suggestions: string[];
  context?: string | null;
  session_id?: string;
}
/**
 * Calls the chat API with the given message and session ID.
 * @param message The user's message to send to the chatbot.
 * @param sessionId Optional session ID for tracking conversation state.
 * @returns A promise that resolves with the chatbot's response.
 */
async function callChat(
  message: string,
  sessionId?: string
): Promise<ChatResult> {
  const res = await fetch('http://localhost:8000/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}


// async function callSimpleChat(
//   message: string,
//   sessionId?: string,
// ): Promise<{ response: string }> {
//   const res = await fetch(
//      `${import.meta.env.VITE_API_BASE}/api/v1/chat`,   // e.g. http://localhost:8000/api
//     {
//       method: 'POST',
//       headers: { 'Content-Type': 'application/json' },
//       body: JSON.stringify({ message, session_id: sessionId }),
//     },
//   );

//   if (!res.ok) {                     // 4xx / 5xx guard
//     throw new Error(`HTTP ${res.status}`);
//   }
//   const data = await res.json();     // <== {response, status, …}

//   if (data.status !== 'success') {   // backend-level error
//     throw new Error(data.response ?? 'Unknown error');
//   }
//   return data;                       // {response: "..."}
// }

const handleSendMessage = async () => {
  if (!inputValue.trim()) return;

  // 1️⃣ Add the user’s message to chat
  const userMsg = {
    id: Date.now(),
    type: 'user',
    content: inputValue,
    timestamp: new Date(),
  };
  setMessages(prev => [...prev, userMsg]);
  setInputValue('');
  setIsLoading(true);

  try {
    // 2️⃣ Build payload (with optional CSV)
    const payload = {
      message: inputValue,
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
    const response = await fetch('http://localhost:8000/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const { response: aiText, suggestions, context } = await response.json();

    // 4️⃣ Build the assistant’s message
    const aiMsg = {
      id: Date.now() + 1,
      type: 'assistant',
      content: aiText,
      timestamp: new Date(),
      // Attach context (if any) so you can render it
      context,
      // Attach suggestions array (if any)
      suggestions: suggestions || [],
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

//////

//////Previous mock response code

//   const handleSendMessage = async () => {
//     if (!inputValue.trim()) return;

//     const userMessage = {
//       id: Date.now(),
//       type: 'user',
//       content: inputValue,
//       timestamp: new Date()
//     };

//     setMessages(prev => [...prev, userMessage]);
//     setInputValue('');
//     setIsLoading(true);

    


//     setTimeout(() => {
//       const assistantMessage = {
//         id: Date.now() + 1,
//         type: 'assistant',
//         content: generateMockResponse(inputValue),
//         timestamp: new Date()
//       };
      
//       setMessages(prev => [...prev, assistantMessage]);
//       setIsLoading(false);
//      }, 2500);
//   };
// const generateMockResponse = (query: string): string => { return "Timeout: "+query; }


  // const generateMockResponse = (query: string): string => {
  //   const lowerQuery = query.toLowerCase();
  //   if (lowerQuery.includes('spending') || lowerQuery.includes('cost')) {
  //     return "Based on your purchase order data, total spending on the requested items is $1,120.75. This represents a 15% increase compared to the previous period.";
  //   } else if (lowerQuery.includes('vendor') || lowerQuery.includes('supplier')) {
  //     return "MedSupply Co is your top vendor with 3 orders totaling $640.25, followed by FluidTech with $275.50. MedSupply Co offers competitive pricing for surgical supplies.";
  //   } else if (lowerQuery.includes('department')) {
  //     return "Surgery department has the highest procurement activity with 2 major orders. Emergency and ICU departments follow with significant medical supply purchases.";
  //   } else {
  //     return "I've analyzed your purchase order data. Could you please be more specific about what you'd like to know? I can help with spending analysis, vendor comparisons, or departmental insights.";
  //   }
  // };

  interface SuggestionClickEvent {
    (suggestion: string): void;
  }

  const handleSuggestionClick: SuggestionClickEvent = (suggestion: string) => {
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
    }
  };

  return (
    <div style={styles.container}>
      {/* Side */}
      <div style={styles.sidebar}>
        {/* Head */}
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

        {/* uploadarea */}
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
            </div>
          )}


          {uploadedFile && currentBatch && (
            <button
              onClick={async () => {
                const data = await fetchBatchData(currentBatch);
                console.log("🔄 refreshed data:", data);
                setFileData(data);
                setShowFilePreview(true);
              }}
              style={{
                marginTop: '8px',
                padding: '8px 12px',
                backgroundColor: '#2563eb',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              Refresh Data from Cosmos
            </button>
          )}

        </div>

        {/* preview */}
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
                    {fileData?.slice(0, 3).map((row) => (
                      <tr key={row.id}>
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

        {/* searching suggestion */}
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
        </div>
      </div>

      {/* main chart area */}
      <div style={styles.mainArea}>
        {/* chart head */}
        <div style={styles.chatHeader}>
          <div style={styles.chatHeaderContent}>
            <div>
              <h2 style={styles.chatTitle}>Purchase Order Analysis</h2>
              <p style={styles.chatSubtitle}>Ask Earl about your procurement data</p>
            </div>
            <div style={styles.chatActions}>
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

        {/* massage area */}
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
                  {message.type === 'user' ? <Icons.User /> : <Icons.Bot />}
                </div>
                <div
                  style={{
                    ...styles.bubble,
                    ...(message.type === 'user' ? styles.bubbleUser :
                        message.type === 'system' ? styles.bubbleSystem : styles.bubbleAssistant)
                  }}
                >
                  <p style={styles.messageText}>{message.content}</p>
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
                <div style={styles.avatarAssistant}>
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

        {/* input area */}
        <div style={styles.inputArea}>
          <div style={styles.inputContainer}>
            <div style={styles.inputWrapper}>
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask Earl about your purchase data..."
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
            Earl can analyze your procurement data, compare vendors, and provide spending insights.
          </p>
        </div>
      </div>

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