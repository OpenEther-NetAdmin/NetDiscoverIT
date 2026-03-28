import React from 'react';
import { Box, Text, Link, Badge, Icon, Flex } from '@chakra-ui/react';
import { FiExternalLink, FiFile, FiDatabase } from 'react-icons/fi';

const TYPE_ICONS = {
  device: FiDatabase,
  external: FiExternalLink,
  document: FiFile,
  unknown: FiFile,
};

const TYPE_COLORS = {
  device: 'blue',
  external: 'teal',
  document: 'purple',
  unknown: 'gray',
};

const SourceCard = ({ source, hostname, similarity: similarityProp, url: urlProp }) => {
  if (!source && !hostname) return null;

  const title = source?.title || hostname || 'Unknown';
  const url = source?.url || urlProp;
  const snippet = source?.snippet;
  const type = source?.type || 'device';
  const similarity = source?.similarity ?? similarityProp;
  const TypeIcon = TYPE_ICONS[type] || FiFile;
  const colorScheme = TYPE_COLORS[type] || 'gray';

  const content = (
    <Box
      p={3}
      borderWidth="1px"
      borderRadius="md"
      borderColor="gray.200"
      bg="white"
      _hover={url ? { bg: 'gray.50', borderColor: 'gray.300' } : {}}
      transition="all 0.15s"
      minW="200px"
      maxW="320px"
    >
      <Flex align="center" gap={2} mb={1}>
        <Icon as={TypeIcon} boxSize={4} color={`${colorScheme}.500`} />
        <Text
          fontWeight="semibold"
          fontSize="sm"
          color="gray.700"
          noOfLines={1}
          flex={1}
        >
          {title}
        </Text>
        {url && <Icon as={FiExternalLink} boxSize={3} color="gray.400" />}
      </Flex>

      {snippet && (
        <Text fontSize="xs" color="gray.500" noOfLines={2} mb={1}>
          {snippet}
        </Text>
      )}

      <Flex gap={2} align="center">
        <Badge colorScheme={colorScheme} variant="subtle" fontSize="xs">
          {type}
        </Badge>
        {typeof similarity === 'number' && similarity > 0 && (
          <Text fontSize="xs" color="gray.400">
            {Math.round(similarity * 100)}% match
          </Text>
        )}
      </Flex>
    </Box>
  );

  if (url) {
    return (
      <Link
        href={url}
        isExternal
        _hover={{ textDecoration: 'none' }}
        display="inline-block"
      >
        {content}
      </Link>
    );
  }

  return content;
};

export default SourceCard;
