import React from 'react';
import { Box, SimpleGrid, Stat, StatLabel, StatNumber, StatHelpText, Card, CardHeader, Heading, CardBody, Table, Thead, Tbody, Tr, Th, Td, Badge } from '@chakra-ui/react';

const Dashboard = () => {
  // Mock data
  const stats = {
    totalDevices: 42,
    activeDiscoveries: 2,
    issues: 5,
    lastDiscovery: '2026-03-01 14:30:00'
  };

  const recentDevices = [
    { hostname: 'core-rtr-01', ip: '10.0.0.1', type: 'router', vendor: 'cisco', status: 'online' },
    { hostname: 'core-sw-01', ip: '10.0.0.2', type: 'switch', vendor: 'cisco', status: 'online' },
    { hostname: 'dist-sw-01', ip: '10.0.0.3', type: 'switch', vendor: 'arista', status: 'online' },
    { hostname: 'fw-edge-01', ip: '10.0.0.4', type: 'firewall', vendor: 'palo_alto', status: 'warning' },
  ];

  return (
    <Box p={6}>
      <Heading size="lg" mb={6}>Dashboard</Heading>
      
      {/* Stats */}
      <SimpleGrid columns={{ base: 1, md: 2, lg: 4 }} spacing={4} mb={6}>
        <Card>
          <CardBody>
            <Stat>
              <StatLabel>Total Devices</StatLabel>
              <StatNumber>{stats.totalDevices}</StatNumber>
              <StatHelpText>Across all networks</StatHelpText>
            </Stat>
          </CardBody>
        </Card>
        
        <Card>
          <CardBody>
            <Stat>
              <StatLabel>Active Discoveries</StatLabel>
              <StatNumber>{stats.activeDiscoveries}</StatNumber>
              <StatHelpText>Running now</StatHelpText>
            </Stat>
          </CardBody>
        </Card>
        
        <Card>
          <CardBody>
            <Stat>
              <StatLabel>Issues</StatLabel>
              <StatNumber color="orange.500">{stats.issues}</StatNumber>
              <StatHelpText>Requires attention</StatHelpText>
            </Stat>
          </CardBody>
        </Card>
        
        <Card>
          <CardBody>
            <Stat>
              <StatLabel>Last Discovery</StatLabel>
              <StatNumber fontSize="lg">{stats.lastDiscovery}</StatNumber>
              <StatHelpText>2 hours ago</StatHelpText>
            </Stat>
          </CardBody>
        </Card>
      </SimpleGrid>
      
      {/* Recent Devices */}
      <Card>
        <CardHeader>
          <Heading size="md">Recent Devices</Heading>
        </CardHeader>
        <CardBody>
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th>Hostname</Th>
                <Th>IP Address</Th>
                <Th>Type</Th>
                <Th>Vendor</Th>
                <Th>Status</Th>
              </Tr>
            </Thead>
            <Tbody>
              {recentDevices.map((device) => (
                <Tr key={device.hostname}>
                  <Td fontWeight="medium">{device.hostname}</Td>
                  <Td>{device.ip}</Td>
                  <Td>{device.type}</Td>
                  <Td>{device.vendor}</Td>
                  <Td>
                    <Badge colorScheme={device.status === 'online' ? 'green' : 'orange'}>
                      {device.status}
                    </Badge>
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

export default Dashboard;
