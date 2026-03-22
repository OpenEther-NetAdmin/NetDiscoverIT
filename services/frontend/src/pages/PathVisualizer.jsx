import React, { useState, useCallback } from 'react';
import { Box, Heading, Flex, Input, Button, Card, CardBody, CardHeader, VStack, HStack, Badge, Text, Table, Thead, Tbody, Tr, Th, Td, Icon, useToast } from '@chakra-ui/react';
import ReactFlow, { Background, Controls, MiniMap, useNodesState, useEdgesState, addEdge } from 'reactflow';
import 'reactflow/dist/style.css';
import { FiNavigation, FiCheck, FiAlertTriangle, FiInfo } from 'react-icons/fi';
import api from '../services/api';

const PathVisualizer = () => {
  const [sourceIP, setSourceIP] = useState('');
  const [destIP, setDestIP] = useState('');
  const [path, setPath] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  
  const [nodes, setNodes, onNodesChange] = useNodesState([
    { id: '1', position: { x: 100, y: 100 }, data: { label: 'SW-ACCESS-1' }, type: 'default', style: { background: '#E2E8F0', padding: 10, borderRadius: 5 } },
    { id: '2', position: { x: 300, y: 50 }, data: { label: 'RTR-CORE-1' }, type: 'default', style: { background: '#90CDF4', padding: 10, borderRadius: 5 } },
    { id: '3', position: { x: 500, y: 100 }, data: { label: 'FW-EDGE-1' }, type: 'default', style: { background: '#FEB2B2', padding: 10, borderRadius: 5 } },
    { id: '4', position: { x: 700, y: 50 }, data: { label: 'SW-DB-1' }, type: 'default', style: { background: '#E2E8F0', padding: 10, borderRadius: 5 } },
    { id: '5', position: { x: 700, y: 150 }, data: { label: 'DB-SERVER' }, type: 'default', style: { background: '#C6F6D5', padding: 10, borderRadius: 5 } },
  ]);
  
  const [edges, setEdges, onEdgesChange] = useEdgesState([
    { id: 'e1-2', source: '1', target: '2', label: 'VLAN 10', animated: true },
    { id: 'e2-3', source: '2', target: '3', label: 'VLAN 20→99', animated: true },
    { id: 'e3-4', source: '3', target: '4', label: 'DMZ', animated: true },
    { id: 'e4-5', source: '4', target: '5', label: 'VLAN 30', animated: true },
  ]);

  const tracePath = async () => {
    if (!sourceIP || !destIP) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await api.tracePath(sourceIP, destIP);
      
      if (result.path_found) {
        setPath({
          found: true,
          hops: result.hops.map((hop, index) => ({
            hop: hop.hop,
            device: hop.device?.hostname || 'Unknown',
            interface: hop.interface?.name || 'Unknown',
            vlan: hop.interface?.vlan_id || 'N/A',
            type: 'device',
          })),
          summary: {
            totalHops: result.summary?.path_length || result.hops.length,
            vlanChanges: 0,
            zoneChanges: 0,
            estimatedLatency: 'N/A',
            natApplied: false
          },
          issues: result.issues || []
        });
        
        toast({
          title: 'Path traced successfully',
          status: 'success',
          duration: 3000,
        });
      } else {
        setPath({
          found: false,
          hops: [],
          summary: result.summary || {},
          issues: result.issues || [{ severity: 'warning', message: result.summary?.error || 'No path found' }]
        });
        
        toast({
          title: 'No path found',
          description: result.summary?.error || 'Could not find a path between the specified devices',
          status: 'warning',
          duration: 5000,
        });
      }
    } catch (err) {
      setError(err.message);
      toast({
        title: 'Path trace failed',
        description: err.message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const getIssueIcon = (severity) => {
    switch (severity) {
      case 'warning': return FiAlertTriangle;
      case 'error': return FiAlertTriangle;
      default: return FiInfo;
    }
  };

  const getIssueColor = (severity) => {
    switch (severity) {
      case 'warning': return 'orange';
      case 'error': return 'red';
      default: return 'blue';
    }
  };

  return (
    <Box p={6} h="calc(100vh - 48px)">
      <Heading size="lg" mb={4}>Path Visualizer</Heading>
      
      {/* Controls */}
      <Card mb={4}>
        <CardBody>
          <Flex gap={4} align="center">
            <Input 
              placeholder="Source IP (e.g., 10.1.1.50)" 
              maxW="200px"
              value={sourceIP}
              onChange={(e) => setSourceIP(e.target.value)}
            />
            <Box>→</Box>
            <Input 
              placeholder="Destination IP (e.g., 10.20.30.10)" 
              maxW="200px"
              value={destIP}
              onChange={(e) => setDestIP(e.target.value)}
            />
            <Button 
              leftIcon={<FiNavigation />} 
              colorScheme="blue" 
              onClick={tracePath}
              isLoading={loading}
              loadingText="Tracing"
            >
              Trace Path
            </Button>
          </Flex>
        </CardBody>
      </Card>
      
      <Flex gap={4} h="calc(100% - 140px)">
        {/* Network Map */}
        <Box flex="1" bg="white" borderRadius="md" border="1px" borderColor="gray.200" overflow="hidden">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </Box>
        
        {/* Path Details */}
        {path && (
          <Card w="400px" overflow="auto">
            <CardHeader>
              <Heading size="md">Path Details</Heading>
            </CardHeader>
            <CardBody pt={0}>
              {/* Summary */}
              <Box mb={4}>
                <Text fontWeight="semibold" mb={2}>Summary</Text>
                <HStack spacing={4} flexWrap="wrap">
                  <Badge colorScheme="blue">Hops: {path.summary.totalHops}</Badge>
                  <Badge colorScheme="purple">VLANs: {path.summary.vlanChanges}</Badge>
                  <Badge colorScheme="orange">Zones: {path.summary.zoneChanges}</Badge>
                  <Badge colorScheme="green">{path.summary.estimatedLatency}</Badge>
                  {path.summary.natApplied && <Badge colorScheme="teal">NAT</Badge>}
                </HStack>
              </Box>
              
              {/* Hop Table */}
              <Box mb={4}>
                <Text fontWeight="semibold" mb={2}>Hops</Text>
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr>
                      <Th>#</Th>
                      <Th>Device</Th>
                      <Th>Interface</Th>
                      <Th>VLAN</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {path.hops.map((hop) => (
                      <Tr key={hop.hop}>
                        <Td>{hop.hop}</Td>
                        <Td>
                          <Text fontWeight="medium">{hop.device}</Text>
                          <Text fontSize="xs" color="gray.500">{hop.type}</Text>
                        </Td>
                        <Td fontSize="xs">{hop.interface}</Td>
                        <Td fontSize="xs">{hop.vlan}</Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </Box>
              
              {/* Issues */}
              {path.issues && path.issues.length > 0 && (
                <Box>
                  <Text fontWeight="semibold" mb={2}>Analysis</Text>
                  <VStack align="stretch" spacing={2}>
                    {path.issues.map((issue, i) => (
                      <Flex 
                        key={i} 
                        p={2} 
                        bg={`${getIssueColor(issue.severity || 'info')}.50`} 
                        borderRadius="md"
                        align="center"
                        gap={2}
                      >
                        <Icon as={getIssueIcon(issue.severity || 'info')} color={`${getIssueColor(issue.severity || 'info')}.500`} />
                        <Text fontSize="sm">{issue.message || issue.type}</Text>
                      </Flex>
                    ))}
                  </VStack>
                </Box>
              )}
            </CardBody>
          </Card>
        )}
      </Flex>
    </Box>
  );
};

export default PathVisualizer;
