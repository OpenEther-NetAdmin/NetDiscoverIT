import React, { useState, useRef, useCallback } from 'react';
import {
  Box, Flex, Heading, Text, Textarea, IconButton,
  Spinner, Button, useToast,
} from '@chakra-ui/react';
import { FiSend } from 'react-icons/fi';
import api from '../../services/api';
import ChatMessage from './ChatMessage';

const AssistantPage = () => {
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = useCallback(async () => {
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;

    const userMsg = { id: crypto.randomUUID(), role: 'user', text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion('');
    setIsLoading(true);

    try {
      const result = await api.queryAssistant({ question: trimmed, top_k: 5 });
      const assistantMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        answer: result.answer,
        sources: result.sources || [],
        confidence: result.confidence,
        query_type: result.query_type,
        retrieved_device_count: result.retrieved_device_count,
        graph_traversal_used: result.graph_traversal_used,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errMsg = {
        id: crypto.randomUUID(),
        role: 'error',
        text: err.message === 'NLI service not available: ANTHROPIC_API_KEY is not configured'
          ? 'AI assistant is temporarily unavailable'
          : `Could not answer: ${err.message}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
      setTimeout(scrollToBottom, 50);
    }
  }, [question, isLoading]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => setMessages([]);

  return (
    <Flex direction="column" h="100%" p={6} gap={4}>
      <Flex justify="space-between" align="center">
        <Box>
          <Heading size="lg">Network Assistant</Heading>
          <Text fontSize="sm" color="gray.500" mt={1}>
            Ask anything about your network — devices, topology, compliance, or changes.
          </Text>
        </Box>
        {messages.length > 0 && (
          <Button size="sm" variant="ghost" onClick={handleClear}>
            Clear conversation
          </Button>
        )}
      </Flex>

      <Box flex="1" overflowY="auto" pr={1}>
        {messages.length === 0 && (
          <Flex h="100%" align="center" justify="center" direction="column" gap={3} color="gray.400">
            <Text fontSize="lg">Ask a question to get started</Text>
            <Text fontSize="sm">e.g. "Which devices are in PCI scope?" or "Show me my routers"</Text>
          </Flex>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {isLoading && (
          <Flex justify="flex-start" mb={4} align="center" gap={2}>
            <Spinner size="sm" />
            <Text fontSize="sm" color="gray.500">Thinking…</Text>
          </Flex>
        )}
        <div ref={messagesEndRef} />
      </Box>

      <Flex gap={2} align="flex-end" flexShrink={0}>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your network… (Enter to send, Shift+Enter for newline)"
          rows={1}
          resize="none"
          maxH="80px"
          overflowY="auto"
          flex="1"
          isDisabled={isLoading}
          aria-label="Chat input"
        />
        <IconButton
          aria-label="Send message"
          icon={isLoading ? <Spinner size="sm" /> : <FiSend />}
          colorScheme="blue"
          isDisabled={!question.trim() || isLoading}
          onClick={handleSend}
          flexShrink={0}
        />
      </Flex>
    </Flex>
  );
};

export default AssistantPage;
