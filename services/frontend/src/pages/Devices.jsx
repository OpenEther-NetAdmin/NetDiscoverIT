import React, { useState, useEffect } from 'react';
import { Box, Heading, Table, Thead, Tbody, Tr, Th, Td, Badge, Input, InputGroup, InputLeftElement, Select, Button, Flex, Card, CardBody, useDisclosure, Spinner, Text } from '@chakra-ui/react';
import { FiSearch, FiRefreshCw, FiPlus } from 'react-icons/fi';
import api from '../services/api';

const Devices = () => {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getDevices();
      setDevices(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredDevices = devices.filter(d => {
    const matchesSearch = d.hostname?.toLowerCase().includes(search.toLowerCase()) || d.management_ip?.includes(search);
    const matchesFilter = filter === 'all' || d.status === filter;
    return matchesSearch && matchesFilter;
  });

  const getStatusColor = (status) => {
    switch (status) {
      case 'online': return 'green';
      case 'warning': return 'orange';
      case 'offline': return 'red';
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

  if (error) {
    return (
      <Box p={6}>
        <Text color="red.500">{error}</Text>
        <Button mt={4} onClick={loadDevices}>Retry</Button>
      </Box>
    );
  }

  return (
    <Box p={6}>
      <Flex justify="space-between" align="center" mb={6}>
        <Heading size="lg">Devices</Heading>
        <Flex gap={2}>
          <Button leftIcon={<FiRefreshCw />} variant="outline" onClick={loadDevices}>Refresh</Button>
          <Button leftIcon={<FiPlus />} colorScheme="blue">Add Device</Button>
        </Flex>
      </Flex>
      
      <Card mb={4}>
        <CardBody>
          <Flex gap={4}>
            <InputGroup maxW="300px">
              <InputLeftElement>
                <FiSearch color="gray" />
              </InputLeftElement>
              <Input 
                placeholder="Search devices..." 
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </InputGroup>
            <Select maxW="150px" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All Status</option>
              <option value="online">Online</option>
              <option value="warning">Warning</option>
              <option value="offline">Offline</option>
            </Select>
          </Flex>
        </CardBody>
      </Card>
      
      <Card>
        <CardBody p={0}>
          <Table variant="simple">
            <Thead>
              <Tr>
                <Th>Hostname</Th>
                <Th>IP Address</Th>
                <Th>Vendor</Th>
                <Th>Type</Th>
                <Th>Role</Th>
                <Th>Status</Th>
                <Th>Last Seen</Th>
              </Tr>
            </Thead>
            <Tbody>
              {filteredDevices.map((device) => (
                <Tr key={device.id} _hover={{ bg: 'gray.50' }} cursor="pointer">
                  <Td fontWeight="medium">{device.hostname}</Td>
                  <Td fontFamily="mono" fontSize="sm">{device.management_ip}</Td>
                  <Td textTransform="capitalize">{device.vendor?.replace('_', ' ')}</Td>
                  <Td textTransform="capitalize">{device.device_type}</Td>
                  <Td textTransform="capitalize">{device.role}</Td>
                  <Td>
                    <Badge colorScheme={getStatusColor(device.status || 'online')}>
                      {device.status || 'online'}
                    </Badge>
                  </Td>
                  <Td fontSize="sm" color="gray.500">
                    {device.updated_at ? new Date(device.updated_at).toLocaleString() : 'N/A'}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </CardBody>
      </Card>
    </Box>
  );
};

export default Devices;
