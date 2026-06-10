"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Clock, Zap, Sparkles } from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  isError?: boolean;
  meta?: {
    latency?: number;
    tokens?: number;
  };
}

export default function Playground() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isSending]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMsg: Message = { role: 'user', content: inputValue.trim() };
    const newMessages = [...messages, userMsg];

    setMessages(newMessages);
    setInputValue('');
    setIsSending(true);

    const payload = {
      model: 'auto',
      messages: newMessages.map(m => ({ role: m.role, content: m.content }))
    };

    try {
      const startTime = Date.now();
      const response = await fetch('http://localhost:4000/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      const endTime = Date.now();

      if (data.error) {
        setMessages(prev => [...prev, { role: 'assistant', content: data.error, isError: true }]);
      } else {
        const content = data.choices && data.choices[0] ? data.choices[0].message.content : "No content returned.";
        const meta = {
          latency: endTime - startTime,
          tokens: data.usage?.total_tokens
        };
        setMessages(prev => [...prev, { role: 'assistant', content, meta }]);
      }
    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: err.message || 'Failed to connect to gateway', isError: true }]);
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

  return (
    <div className="flex flex-col h-full w-full relative">
      {/* Dynamic Background Glow for Initial State */}
      {isInitialState && (
        <div className="absolute inset-0 overflow-hidden flex items-center justify-center pointer-events-none">
          <div 
            className="w-[80vw] h-[80vw] max-w-[800px] max-h-[800px]"
            style={{ background: 'radial-gradient(circle, rgba(59, 130, 246, 0.08) 0%, transparent 60%)' }} 
          />
        </div>
      )}

      {/* Main Content Area */}
      <div className={`flex-1 flex flex-col overflow-hidden relative z-10 items-center ${isInitialState ? 'justify-center' : 'justify-start'}`}>
        {isInitialState ? (
          <div className="w-full flex flex-col items-center px-5">
            <h1 className="text-[2.5rem] font-normal text-[#e5e7eb] mb-10 tracking-tight font-sans">
              {greeting}
            </h1>

            {/* Initial Pill Input */}
            <div className="w-full max-w-[800px] relative">
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
            <div className="mt-6 text-sm text-gray-500 font-medium">
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
  );
}
