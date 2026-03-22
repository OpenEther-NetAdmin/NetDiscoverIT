import React, { useState, useEffect } from 'react';
import { Box, Heading, Card, CardBody, CardHeader, Button, Badge, Table, Thead, Tbody, Tr, Th, Td, Flex, Text, Progress, VStack, Spinner, useToast } from '@chakra-ui/react';
import { FiPlay, FiClock, FiCheckCircle, FiXCircle } from 'react-icons/fi';
import api from '../services/api';

const Discoveries = () => {
  const [discoveries, setDiscoveries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const toast = useToast();

  useEffect(() => {
    loadDiscoveries();
  }, []);

  const loadDiscoveries = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getDiscoveries();
      setDiscoveries(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const createDiscovery = async () => {
    try {
      setCreating(true);
      await api.createDiscovery({
        name: 'New Discovery',
        discovery_type: 'full',
      });
      toast({
        title: 'Discovery started',
        status: 'success',
        duration: 3000,
      });
      await loadDiscoveries();
    } catch (err) {
      toast({
        title: 'Failed to start discovery',
        description: err.message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setCreating(false);
    }
  };

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

  if (loading) {
    return (
      <Box p={6}>
        <Flex justify="center" align="center" h="400px">
          <Spinner size="xl" />
        </Flex>
      </Box>
    );
  }

  return (
    <Box p={6}>
      <Flex justify="space-between" align="center" mb={6}>
        <Heading size="lg">Discoveries</Heading>
        <Button leftIcon={<FiPlay />} colorScheme="blue" onClick={createDiscovery} isLoading={creating}>
          New Discovery
        </Button>
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
                  <Progress value={discovery.progress || 0} colorScheme="blue" size="sm" borderRadius="full" />
                  <Text fontSize="sm" color="gray.500" mt={2}>
                    {discovery.device_count || 0} devices discovered
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
                <Th>Completed</Th>
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
                  <Td>{discovery.device_count || 0}</Td>
                  <Td fontSize="sm">{discovery.created_at ? new Date(discovery.created_at).toLocaleString() : '-'}</Td>
                  <Td fontSize="sm">{discovery.completed_at ? new Date(discovery.completed_at).toLocaleString() : '-'}</Td>
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
