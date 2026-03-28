import React from 'react';
import {
  Box, Flex, Text, Badge, Progress, Wrap, WrapItem, Icon,
  UnorderedList, ListItem,
} from '@chakra-ui/react';
import { FiGitBranch, FiAlertTriangle } from 'react-icons/fi';
import ReactMarkdown from 'react-markdown';
import SourceCard from './SourceCard';
import { QUERY_TYPE_COLORS, confidenceColor } from './assistantUtils';

const markdownComponents = {
  p: ({ children }) => <Text fontSize="sm" mb={2}>{children}</Text>,
  ul: ({ children }) => <UnorderedList mb={2} pl={4}>{children}</UnorderedList>,
  li: ({ children }) => <ListItem fontSize="sm">{children}</ListItem>,
  strong: ({ children }) => <Text as="span" fontWeight="bold">{children}</Text>,
};

const ChatMessage = ({ message }) => {
  if (message.role === 'user') {
    return (
      <Flex justify="flex-end" mb={4}>
        <Box
          bg="blue.500"
          color="white"
          borderRadius="lg"
          px={4}
          py={2}
          maxW="70%"
          fontSize="sm"
        >
          {message.text}
        </Box>
      </Flex>
    );
  }

  if (message.role === 'error') {
    return (
      <Flex justify="flex-start" mb={4} align="center" gap={2}>
        <Icon as={FiAlertTriangle} color="red.400" />
        <Text fontSize="sm" color="red.500">{message.text}</Text>
      </Flex>
    );
  }

  const colorScheme = confidenceColor(message.confidence);
  const queryColor = QUERY_TYPE_COLORS[message.query_type] || 'gray';

  return (
    <Flex justify="flex-start" mb={4}>
      <Box
        bg="white"
        border="1px"
        borderColor="gray.200"
        borderRadius="lg"
        p={4}
        w="100%"
        boxShadow="sm"
      >
        <Flex justify="flex-end" mb={2}>
          <Badge colorScheme={queryColor} variant="subtle" textTransform="capitalize">
            {message.query_type || 'query'}
          </Badge>
        </Flex>

        <Box mb={3}>
          {message.answer
            ? <ReactMarkdown components={markdownComponents}>{message.answer}</ReactMarkdown>
            : <Text fontSize="sm" color="gray.500">(no answer)</Text>
          }
        </Box>

        <Flex align="center" gap={2} mb={3}>
          <Progress
            value={(message.confidence || 0) * 100}
            colorScheme={colorScheme}
            size="xs"
            flex="1"
            borderRadius="full"
          />
          <Text fontSize="xs" color="gray.500" flexShrink={0}>
            {Math.round((message.confidence || 0) * 100)}%
          </Text>
        </Flex>

        {message.graph_traversal_used && (
          <Flex align="center" gap={1} mb={2} color="gray.500">
            <Icon as={FiGitBranch} boxSize={3} />
            <Text fontSize="xs">Graph traversal used</Text>
          </Flex>
        )}

        {message.sources?.length > 0 && (
          <Wrap spacing={2}>
            {message.sources.map((src) => (
              <WrapItem key={src.device_id}>
                <SourceCard hostname={src.hostname} similarity={src.similarity} />
              </WrapItem>
            ))}
          </Wrap>
        )}
      </Box>
    </Flex>
  );
};

export default ChatMessage;
