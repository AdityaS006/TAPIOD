"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Clock, Zap, Sparkles, Plus, MessageSquare, Trash2, RefreshCw } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  isError?: boolean;
  meta?: {
    latency?: number;
    tokens?: number;
    injected_tools?: string[];
  };
}

interface ChatSession {
  id: string;
  title: string;
  updatedAt: number;
  messages: Message[];
}

export default function Playground() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  
  const [userId] = useState('demo_user');
  const [tenantId] = useState('demo_tenant');
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load from backend
  useEffect(() => {
    const loadSessions = async () => {
      try {
        // Migration logic from LocalStorage
        const localData = localStorage.getItem('tapiod_chat_sessions');
        if (localData) {
          try {
            const parsed = JSON.parse(localData);
            if (Array.isArray(parsed) && parsed.length > 0) {
              for (const session of parsed) {
                await fetch('http://localhost:4001/api/chats', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    ...session,
                    user_id: userId,
                    tenant_id: tenantId
                  })
                });
              }
            }
            localStorage.removeItem('tapiod_chat_sessions');
          } catch (e) {
            console.error("Migration failed", e);
          }
        }

        const res = await fetch(`http://localhost:4001/api/chats?user_id=${userId}&tenant_id=${tenantId}`);
        if (res.ok) {
          const data = await res.json();
          if (!data.error && Array.isArray(data)) {
            setSessions(data);
            if (data.length > 0) {
              setActiveSessionId(data[0].id);
            }
          }
        }
      } catch (err) {
        console.error("Failed to load sessions", err);
      } finally {
        setIsLoaded(true);
      }
    };
    loadSessions();
  }, [userId, tenantId]);

  const saveSession = async (session: ChatSession) => {
    try {
      await fetch('http://localhost:4001/api/chats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...session,
          user_id: userId,
          tenant_id: tenantId
        })
      });
    } catch (e) {
      console.error("Failed to save session", e);
    }
  };

  const activeSession = sessions.find(s => s.id === activeSessionId);
  const messages = activeSession ? activeSession.messages : [];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isSending]);

  const createNewChat = () => {
    setActiveSessionId(null);
  };

  const deleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    const updated = sessions.filter(s => s.id !== id);
    setSessions(updated);
    if (activeSessionId === id) {
      setActiveSessionId(updated.length > 0 ? updated[0].id : null);
    }
    try {
      await fetch(`http://localhost:4001/api/chats/${id}?user_id=${userId}&tenant_id=${tenantId}`, {
        method: 'DELETE'
      });
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMsg: Message = { role: 'user', content: inputValue.trim() };
    
    let currentSessionId = activeSessionId;
    let newSessions = [...sessions];

    if (!currentSessionId) {
      currentSessionId = Date.now().toString();
      const titleWords = userMsg.content.split(' ').slice(0, 4);
      const title = titleWords.join(' ') + (titleWords.length === 4 ? '...' : '');
      const newSession: ChatSession = {
        id: currentSessionId,
        title: title || 'New Chat',
        updatedAt: Date.now(),
        messages: [userMsg]
      };
      newSessions = [newSession, ...newSessions];
      setActiveSessionId(currentSessionId);
    } else {
      newSessions = newSessions.map(s => {
        if (s.id === currentSessionId) {
          return { ...s, messages: [...s.messages, userMsg], updatedAt: Date.now() };
        }
        return s;
      });
    }

    setSessions(newSessions);
    const updatedSession = newSessions.find(s => s.id === currentSessionId);
    if (updatedSession) saveSession(updatedSession);

    setInputValue('');
    setIsSending(true);

    const activeMessages = newSessions.find(s => s.id === currentSessionId)?.messages || [];

    const payload: any = {
      model: 'auto',
      messages: activeMessages.map(m => ({ role: m.role, content: m.content }))
    };

    await sendPayload(payload, currentSessionId, newSessions);
  };

  const handleRegenerate = async (msgIndex: number) => {
    if (!activeSessionId) return;
    const session = sessions.find(s => s.id === activeSessionId);
    if (!session) return;
    
    // Slice up to but NOT including the assistant message (so we keep the user message)
    const newMessages = session.messages.slice(0, msgIndex);
    
    const newSessions = sessions.map(s => {
      if (s.id === activeSessionId) {
        return { ...s, messages: newMessages, updatedAt: Date.now() };
      }
      return s;
    });
    
    setSessions(newSessions);
    setIsSending(true);

    const payload: any = {
      model: 'auto',
      messages: newMessages.map(m => ({ role: m.role, content: m.content })),
      metadata: { bypass_cache: true }
    };
    
    await sendPayload(payload, activeSessionId, newSessions);
  };

  const sendPayload = async (payload: any, currentSessionId: string, newSessions: ChatSession[]) => {

    try {
      const startTime = Date.now();
      const response = await fetch('http://localhost:4001/api/agent/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      const endTime = Date.now();

      const updatedSessions = [...newSessions];
      const sessionIndex = updatedSessions.findIndex(s => s.id === currentSessionId);
      
      if (sessionIndex >= 0) {
        let injectedTools: string[] = [];
        try {
          const toolsRes = await fetch(`http://localhost:4001/api/last_tools?tenant_id=${tenantId}&t=${Date.now()}`, {
            cache: 'no-store'
          });
          if (toolsRes.ok) {
            const toolsData = await toolsRes.json();
            injectedTools = toolsData.tools || [];
          }
        } catch (e) {
          console.error("Failed to fetch injected tools", e);
        }

        if (data.error) {
          const errorMsg = typeof data.error === 'object' ? data.error.message || JSON.stringify(data.error) : String(data.error);
          updatedSessions[sessionIndex].messages.push({ 
            role: 'assistant', 
            content: "LLM Error: " + errorMsg, 
            isError: true,
            meta: { injected_tools: injectedTools, latency: endTime - startTime }
          });
        } else {
          let content = data.choices && data.choices[0] ? data.choices[0].message.content : null;
          if (!content && data.choices && data.choices[0]?.message?.tool_calls) {
            content = "LLM generated Tool Calls:\n" + JSON.stringify(data.choices[0].message.tool_calls, null, 2);
          } else if (!content) {
            content = "No content returned.";
          }
          
          const meta = {
            latency: endTime - startTime,
            tokens: data.usage?.total_tokens,
            injected_tools: injectedTools
          };
          updatedSessions[sessionIndex].messages.push({ role: 'assistant', content, meta });
        }
        setSessions(updatedSessions);
        saveSession(updatedSessions[sessionIndex]);
      }
    } catch (err: any) {
      const updatedSessions = [...newSessions];
      const sessionIndex = updatedSessions.findIndex(s => s.id === currentSessionId);
      if (sessionIndex >= 0) {
        updatedSessions[sessionIndex].messages.push({ role: 'assistant', content: err.message || 'Failed to connect to gateway', isError: true });
        setSessions(updatedSessions);
        saveSession(updatedSessions[sessionIndex]);
      }
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isInitialState = messages.length === 0;

  const [greeting] = useState(() => {
    const greetings = [
      "Your move!",
      "Ready to test?",
      "What shall we route today?",
      "Let's build something great.",
      "What's on your mind?",
      "How can TAPIOD help?",
      "Ask me anything."
    ];
    return greetings[Math.floor(Math.random() * greetings.length)];
  });

  if (!isLoaded) return <div className="flex-1 flex items-center justify-center text-gray-500">Loading...</div>;

  return (
    <div className="absolute inset-0 flex overflow-hidden bg-transparent">
      {/* Sidebar for Chat History */}
      <div className="w-[260px] flex-shrink-0 border-r border-white/5 bg-black/20 flex flex-col h-full z-20 relative">
        <div className="p-4">
          <button 
            onClick={createNewChat}
            className="w-full flex items-center gap-2 px-4 py-3 bg-[var(--accent-purple-light)]/10 hover:bg-[var(--accent-purple-light)]/20 text-[var(--accent-purple-light)] rounded-xl transition-colors border border-[var(--accent-purple-light)]/20 font-medium text-sm"
          >
            <Plus size={18} />
            New Session
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto px-2 pb-4 flex flex-col gap-1">
          <div className="px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Recent Chats
          </div>
          {sessions.length === 0 ? (
            <div className="px-3 py-4 text-sm text-gray-600 text-center">No previous sessions</div>
          ) : (
            sessions.map(session => (
              <div 
                key={session.id}
                onClick={() => setActiveSessionId(session.id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                  activeSessionId === session.id 
                    ? 'bg-white/10 text-gray-100' 
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`}
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <MessageSquare size={16} className={activeSessionId === session.id ? 'text-[var(--accent-purple-light)]' : 'text-gray-500'} />
                  <span className="text-sm truncate font-medium">{session.title}</span>
                </div>
                <button 
                  onClick={(e) => deleteSession(e, session.id)}
                  className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all p-1"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full relative">
        {/* Dynamic Background Glow for Initial State */}
        {isInitialState && (
          <div className="absolute inset-0 overflow-hidden flex items-center justify-center pointer-events-none">
            <div 
              className="w-[80vw] h-[80vw] max-w-[800px] max-h-[800px]"
              style={{ background: 'radial-gradient(circle, rgba(59, 130, 246, 0.08) 0%, transparent 60%)' }} 
            />
          </div>
        )}

        <div className={`flex-1 flex flex-col overflow-hidden relative z-10 items-center ${isInitialState ? 'justify-center' : 'justify-start'}`}>
          {isInitialState ? (
            <div className="w-full flex flex-col items-center px-5">
              <h1 className="text-[2.5rem] font-normal text-[#e5e7eb] mb-10 tracking-tight font-sans text-center">
                {greeting}
              </h1>

              {/* Initial Pill Input */}
              <div className="w-full max-w-[750px] relative">
                <div className="flex items-center bg-[#1e1f22] rounded-[32px] py-2 px-3 border border-white/5 shadow-[0_10px_40px_rgba(0,0,0,0.4)]">
                  <div className="pl-4 pr-2 text-gray-400 flex items-center">
                    <Sparkles size={24} />
                  </div>
                  <textarea
                    className="flex-1 bg-transparent border-none py-[14px] px-2 text-[1.1rem] text-gray-100 resize-none outline-none min-h-[30px] max-h-[200px] font-inherit leading-[1.4]"
                    placeholder="Ask TAPIOD..."
                    rows={1}
                    value={inputValue}
                    onChange={(e) => {
                      setInputValue(e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
                    }}
                    onKeyDown={handleKeyDown}
                    disabled={isSending}
                  />
                  <button
                    className={`p-3 rounded-full flex items-center justify-center ml-1 transition-all duration-200 ${
                      inputValue.trim() && !isSending 
                        ? 'bg-white/10 text-white cursor-pointer' 
                        : 'bg-transparent text-gray-600 cursor-not-allowed'
                    }`}
                    onClick={handleSend}
                    disabled={!inputValue.trim() || isSending}
                  >
                    <Send size={20} />
                  </button>
                </div>
              </div>
              <div className="mt-6 text-sm text-gray-500 font-medium text-center">
                Powered by LiteLLM and RouteLLM
              </div>
            </div>
          ) : (
            <div className="w-full max-w-[850px] flex flex-col h-full">
              {/* Chat History */}
              <div className="flex-1 overflow-y-auto px-5 py-6 flex flex-col gap-10">
                {messages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`flex gap-5 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                      <div className={`rounded-full h-10 w-10 flex items-center justify-center shrink-0 overflow-hidden ${
                        msg.role === 'user' ? 'bg-[#2a2a2d] text-gray-300' : 'bg-transparent text-purple-500'
                      }`}>
                        {msg.role === 'user' ? <User size={22} /> : <img src="/logo.png" alt="TAPIOD" className="w-full h-full object-contain" />}
                      </div>

                      <div className="flex flex-col gap-2 pt-2">
                        <div className={`text-[1.05rem] leading-[1.6] whitespace-pre-wrap ${
                          msg.role === 'user' 
                            ? 'bg-[#2a2a2d] text-gray-100 py-3.5 px-6 rounded-3xl rounded-tr-md' 
                            : msg.isError ? 'text-red-500' : 'text-gray-200'
                        }`}>
                          {msg.content}
                        </div>

                        {msg.meta && (
                          <div className="flex flex-col">
                            <div className="flex items-center gap-4 text-[0.8rem] mt-1 text-gray-500 font-mono">
                              {msg.meta.latency && (
                                <span className="flex items-center gap-1.5">
                                  <Clock size={14} /> {(msg.meta.latency / 1000).toFixed(2)}s
                                </span>
                              )}
                              {msg.meta.tokens && (
                                <span className="flex items-center gap-1.5">
                                  <Zap size={14} /> {msg.meta.tokens} tkns
                                </span>
                              )}
                            </div>
                            
                            {msg.meta.injected_tools && msg.meta.injected_tools.length > 0 && (
                              <div className="flex items-center gap-3 mt-4 flex-wrap">
                                <span className="text-[0.65rem] font-bold text-gray-500 uppercase tracking-wider">Injected Tools:</span>
                                {msg.meta.injected_tools.map((tool: string, i: number) => (
                                  <div key={i} className="bg-purple-500/10 border border-purple-500/20 text-purple-300 px-3 py-1 rounded-full text-[0.75rem] font-mono whitespace-nowrap">
                                    {tool}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        
                        {msg.role === 'assistant' && !isSending && idx === messages.length - 1 && (
                          <div className="flex items-center mt-2">
                             <button 
                               onClick={() => handleRegenerate(idx)} 
                               className="text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1.5 text-xs bg-white/5 px-3 py-1.5 rounded-full"
                               title="Bypass Cache and Regenerate"
                             >
                               <RefreshCw size={14} /> Regenerate
                             </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {isSending && (
                  <div className="flex justify-start">
                    <div className="flex gap-5 max-w-[85%]">
                      <div className="rounded-full h-10 w-10 flex items-center justify-center shrink-0 overflow-hidden">
                        <img src="/logo.png" alt="Thinking..." className="w-full h-full object-contain animate-pulse-slow" />
                      </div>
                      <div className="text-[1.05rem] text-gray-400 flex items-center pt-2">
                        Generating response...
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} className="h-6" />
              </div>

              {/* Bottom Input Area */}
              <div className="px-5 pb-8 w-full">
                <div className="flex items-center bg-[#1e1f22] rounded-[32px] py-1.5 px-2.5 border border-white/5 shadow-[0_4px_24px_rgba(0,0,0,0.3)]">
                  <div className="pl-4 pr-2 text-gray-500 flex items-center">
                    <Sparkles size={24} />
                  </div>
                  <textarea
                    className="flex-1 bg-transparent border-none py-3 px-2 text-[1.05rem] text-gray-200 resize-none outline-none min-h-[28px] max-h-[150px] font-inherit leading-[1.4]"
                    placeholder="Ask TAPIOD..."
                    rows={1}
                    value={inputValue}
                    onChange={(e) => {
                      setInputValue(e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${Math.min(e.target.scrollHeight, 150)}px`;
                    }}
                    onKeyDown={handleKeyDown}
                    disabled={isSending}
                  />
                  <button
                    className={`p-2.5 rounded-full flex items-center justify-center ml-1 transition-all duration-200 ${
                      inputValue.trim() && !isSending 
                        ? 'bg-white/10 text-white cursor-pointer' 
                        : 'bg-transparent text-gray-600 cursor-not-allowed'
                    }`}
                    onClick={handleSend}
                    disabled={!inputValue.trim() || isSending}
                  >
                    <Send size={18} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
