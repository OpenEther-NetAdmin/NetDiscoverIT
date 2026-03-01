import React from 'react';
import { Box, Heading, Card, CardBody, CardHeader, FormControl, FormLabel, Input, Select, Button, VStack, Divider, Switch, Text, Flex } from '@chakra-ui/react';

const Settings = () => {
  return (
    <Box p={6} maxW="800px">
      <Heading size="lg" mb={6}>Settings</Heading>
      
      {/* General Settings */}
      <Card mb={6}>
        <CardHeader>
          <Heading size="md">General</Heading>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            <FormControl>
              <FormLabel>Organization Name</FormLabel>
              <Input defaultValue="OpenEther" />
            </FormControl>
            
            <FormControl>
              <FormLabel>Timezone</FormLabel>
              <Select defaultValue="America/New_York">
                <option value="America/New_York">Eastern Time (ET)</option>
                <option value="America/Chicago">Central Time (CT)</option>
                <option value="America/Denver">Mountain Time (MT)</option>
                <option value="America/Los_Angeles">Pacific Time (PT)</option>
                <option value="UTC">UTC</option>
              </Select>
            </FormControl>
          </VStack>
        </CardBody>
      </Card>
      
      {/* Discovery Settings */}
      <Card mb={6}>
        <CardHeader>
          <Heading size="md">Discovery</Heading>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            <FormControl>
              <FormLabel>Scan Interval</FormLabel>
              <Select defaultValue="24h">
                <option value="1h">Every hour</option>
                <option value="6h">Every 6 hours</option>
                <option value="12h">Every 12 hours</option>
                <option value="24h">Daily</option>
                <option value="168h">Weekly</option>
              </Select>
            </FormControl>
            
            <FormControl>
              <FormLabel>Discovery Methods</FormLabel>
              <Select defaultValue="ssh">
                <option value="ssh">SSH Only</option>
                <option value="snmp">SNMP Only</option>
                <option value="both">SSH + SNMP</option>
              </Select>
            </FormControl>
            
            <Divider />
            
            <FormControl display="flex" alignItems="center">
              <FormLabel mb="0">Auto-discover new devices</FormLabel>
              <Switch defaultChecked />
            </FormControl>
            
            <FormControl display="flex" alignItems="center">
              <FormLabel mb="0">Notify on device offline</FormLabel>
              <Switch defaultChecked />
            </FormControl>
          </VStack>
        </CardBody>
      </Card>
      
      {/* API Keys */}
      <Card mb={6}>
        <CardHeader>
          <Heading size="md">API Keys</Heading>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            <FormControl>
              <FormLabel>API Key</FormLabel>
              <Input type="password" defaultValue="ndi_xxxxxxxxxxxxx" />
            </FormControl>
            
            <Button colorScheme="blue" variant="outline">Regenerate API Key</Button>
          </VStack>
        </CardBody>
      </Card>
      
      {/* Danger Zone */}
      <Card borderColor="red.200" borderWidth="1px">
        <CardHeader>
          <Heading size="md" color="red.500">Danger Zone</Heading>
        </CardHeader>
        <CardBody>
          <Flex justify="space-between" align="center">
            <Box>
              <Text fontWeight="medium">Delete All Data</Text>
              <Text fontSize="sm" color="gray.500">This will permanently delete all discovered devices and configurations</Text>
            </Box>
            <Button colorScheme="red" variant="outline">Delete</Button>
          </Flex>
        </CardBody>
      </Card>
    </Box>
  );
};

export default Settings;
