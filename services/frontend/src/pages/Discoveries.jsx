import React from 'react';
import { Box, Heading, Card, CardBody, CardHeader, Button, Badge, Table, Thead, Tbody, Tr, Th, Td, Flex, Text, Progress, VStack } from '@chakra-ui/react';
import { FiPlay, FiClock, FiCheckCircle, FiXCircle } from 'react-icons/fi';

const Discoveries = () => {
  const discoveries = [
    { id: 1, name: 'Full Network Scan', status: 'completed', devices: 42, started: '2026-03-01T14:00:00Z', completed: '2026-03-01T14:30:00Z', duration: '30m' },
    { id: 2, name: 'Quick Scan', status: 'running', devices: 38, started: '2026-03-01T16:00:00Z', progress: 85, duration: null },
    { id: 3, name: 'Weekly Full Scan', status: 'completed', devices: 40, started: '2026-02-22T02:00:00Z', completed: '2026-02-22T02:45:00Z', duration: '45m' },
    { id: 4, name: 'VLAN Update', status: 'failed', devices: 0, started: '2026-03-01T10:00:00Z', completed: null, error: 'SSH connection timeout', duration: null },
  ];

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return FiCheckCircle;
      case 'running': return FiClock;
      case 'failed': return FiXCircle;
      default: return FiClock;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'green';
      case 'running': return 'blue';
      case 'failed': return 'red';
      default: return 'gray';
    }
  };

  return (
    <Box p={6}>
      <Flex justify="space-between" align="center" mb={6}>
        <Heading size="lg">Discoveries</Heading>
        <Button leftIcon={<FiPlay />} colorScheme="blue">New Discovery</Button>
      </Flex>
      
      {/* Running Discoveries */}
      <Card mb={6}>
        <CardHeader>
          <Heading size="md">Active Discoveries</Heading>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            {discoveries.filter(d => d.status === 'running').map((discovery) => (
              <Card key={discovery.id} variant="outline">
                <CardBody>
                  <Flex justify="space-between" align="center" mb={2}>
                    <Text fontWeight="semibold">{discovery.name}</Text>
                    <Badge colorScheme="blue">Running</Badge>
                  </Flex>
                  <Progress value={discovery.progress} colorScheme="blue" size="sm" borderRadius="full" />
                  <Text fontSize="sm" color="gray.500" mt={2}>
                    {discovery.devices} devices discovered • {discovery.progress}% complete
                  </Text>
                </CardBody>
              </Card>
            ))}
            {discoveries.filter(d => d.status === 'running').length === 0 && (
              <Text color="gray.500">No active discoveries</Text>
            )}
          </VStack>
        </CardBody>
      </Card>
      
      {/* Discovery History */}
      <Card>
        <CardHeader>
          <Heading size="md">History</Heading>
        </CardHeader>
        <CardBody p={0}>
          <Table variant="simple">
            <Thead>
              <Tr>
                <Th>Name</Th>
                <Th>Status</Th>
                <Th>Devices</Th>
                <Th>Started</Th>
                <Th>Duration</Th>
              </Tr>
            </Thead>
            <Tbody>
              {discoveries.map((discovery) => (
                <Tr key={discovery.id}>
                  <Td fontWeight="medium">{discovery.name}</Td>
                  <Td>
                    <Badge colorScheme={getStatusColor(discovery.status)}>
                      <Flex align="center" gap={1}>
                        <Box as={getStatusIcon(discovery.status)} />
                        {discovery.status}
                      </Flex>
                    </Badge>
                  </Td>
                  <Td>{discovery.devices}</Td>
                  <Td fontSize="sm">{new Date(discovery.started).toLocaleString()}</Td>
                  <Td>{discovery.duration || '-'}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </CardBody>
      </Card>
    </Box>
  );
};

export default Discoveries;
