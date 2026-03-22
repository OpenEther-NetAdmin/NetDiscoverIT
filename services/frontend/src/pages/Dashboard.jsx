import React, { useState, useEffect } from 'react';
import { Box, SimpleGrid, Stat, StatLabel, StatNumber, StatHelpText, Card, CardHeader, Heading, CardBody, Table, Thead, Tbody, Tr, Th, Td, Badge, Spinner, Flex } from '@chakra-ui/react';
import api from '../services/api';

const Dashboard = () => {
  const [stats, setStats] = useState({
    totalDevices: 0,
    activeDiscoveries: 0,
    issues: 0,
    lastDiscovery: null
  });
  const [recentDevices, setRecentDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const [devices, discoveries] = await Promise.all([
        api.getDevices(),
        api.getDiscoveries()
      ]);
      
      const deviceList = devices || [];
      const discoveryList = discoveries || [];
      const activeDiscoveries = discoveryList.filter(d => d.status === 'running');
      
      setStats({
        totalDevices: deviceList.length,
        activeDiscoveries: activeDiscoveries.length,
        issues: 0,
        lastDiscovery: discoveryList.length > 0 ? discoveryList[0].created_at : null
      });
      
      setRecentDevices(deviceList.slice(0, 5));
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
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
              <StatNumber fontSize="lg">{stats.lastDiscovery ? new Date(stats.lastDiscovery).toLocaleDateString() : 'N/A'}</StatNumber>
              <StatHelpText>{stats.lastDiscovery ? new Date(stats.lastDiscovery).toLocaleTimeString() : 'No discoveries yet'}</StatHelpText>
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
          {recentDevices.length > 0 ? (
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
                  <Tr key={device.id}>
                    <Td fontWeight="medium">{device.hostname}</Td>
                    <Td>{device.management_ip}</Td>
                    <Td>{device.device_type}</Td>
                    <Td>{device.vendor}</Td>
                    <Td>
                      <Badge colorScheme="green">
                        online
                      </Badge>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          ) : (
            <Box p={4} textAlign="center" color="gray.500">
              No devices found. Run a discovery to populate the inventory.
            </Box>
          )}
        </CardBody>
      </Card>
    </Box>
  );
};

export default Dashboard;
