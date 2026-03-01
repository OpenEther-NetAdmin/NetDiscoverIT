import React, { useState } from 'react';
import { Box, Heading, Table, Thead, Tbody, Tr, Th, Td, Badge, Input, InputGroup, InputLeftElement, Select, Button, Flex, Card, CardBody, useDisclosure } from '@chakra-ui/react';
import { FiSearch, FiRefreshCw, FiPlus } from 'react-icons/fi';

const Devices = () => {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  
  // Mock data
  const devices = [
    { id: 1, hostname: 'core-rtr-01', ip: '10.0.0.1', vendor: 'cisco', type: 'router', role: 'core', status: 'online', lastSeen: '2026-03-01T14:30:00Z' },
    { id: 2, hostname: 'core-sw-01', ip: '10.0.0.2', vendor: 'cisco', type: 'switch', role: 'core', status: 'online', lastSeen: '2026-03-01T14:30:00Z' },
    { id: 3, hostname: 'dist-sw-01', ip: '10.0.0.3', vendor: 'arista', type: 'switch', role: 'distribution', status: 'online', lastSeen: '2026-03-01T14:29:00Z' },
    { id: 4, hostname: 'dist-sw-02', ip: '10.0.0.4', vendor: 'arista', type: 'switch', role: 'distribution', status: 'online', lastSeen: '2026-03-01T14:29:00Z' },
    { id: 5, hostname: 'fw-edge-01', ip: '10.0.0.5', vendor: 'palo_alto', type: 'firewall', role: 'edge', status: 'warning', lastSeen: '2026-03-01T14:25:00Z' },
    { id: 6, hostname: 'fw-dmz-01', ip: '10.0.0.6', vendor: 'palo_alto', type: 'firewall', role: 'dmz', status: 'online', lastSeen: '2026-03-01T14:28:00Z' },
    { id: 7, hostname: 'acc-sw-01', ip: '10.0.0.10', vendor: 'cisco', type: 'switch', role: 'access', status: 'online', lastSeen: '2026-03-01T14:27:00Z' },
    { id: 8, hostname: 'acc-sw-02', ip: '10.0.0.11', vendor: 'cisco', type: 'switch', role: 'access', status: 'offline', lastSeen: '2026-03-01T10:00:00Z' },
  ];

  const filteredDevices = devices.filter(d => {
    const matchesSearch = d.hostname.toLowerCase().includes(search.toLowerCase()) || d.ip.includes(search);
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

  return (
    <Box p={6}>
      <Flex justify="space-between" align="center" mb={6}>
        <Heading size="lg">Devices</Heading>
        <Flex gap={2}>
          <Button leftIcon={<FiRefreshCw />} variant="outline">Refresh</Button>
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
                  <Td fontFamily="mono" fontSize="sm">{device.ip}</Td>
                  <Td textTransform="capitalize">{device.vendor.replace('_', ' ')}</Td>
                  <Td textTransform="capitalize">{device.type}</Td>
                  <Td textTransform="capitalize">{device.role}</Td>
                  <Td>
                    <Badge colorScheme={getStatusColor(device.status)}>
                      {device.status}
                    </Badge>
                  </Td>
                  <Td fontSize="sm" color="gray.500">
                    {new Date(device.lastSeen).toLocaleString()}
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
