import React from 'react';
import { NavLink } from 'react-router-dom';
import { Box, VStack, Text, Icon, Flex } from '@chakra-ui/react';
import { FiGrid, FiServer, FiSearch, FiMap, FiSettings } from 'react-icons/fi';

const NavItem = ({ to, icon, children }) => (
  <NavLink to={to} style={{ width: '100%' }}>
    {({ isActive }) => (
      <Flex
        align="center"
        px={4}
        py={3}
        mx={2}
        borderRadius="md"
        color={isActive ? 'blue.500' : 'gray.600'}
        bg={isActive ? 'blue.50' : 'transparent'}
        _hover={{ bg: 'blue.50', color: 'blue.500' }}
        cursor="pointer"
        transition="all 0.2s"
      >
        <Icon as={icon} mr={3} boxSize={5} />
        <Text fontWeight={isActive ? 'semibold' : 'medium'}>{children}</Text>
      </Flex>
    )}
  </NavLink>
);

const Sidebar = () => {
  return (
    <Box w="240px" bg="white" borderRight="1px" borderColor="gray.200" py={4}>
      <Box px={4} mb={6}>
        <Text fontSize="xl" fontWeight="bold" color="blue.600">
          NetDiscoverIT
        </Text>
        <Text fontSize="xs" color="gray.500">
          AI Network Discovery
        </Text>
      </Box>
      
      <VStack spacing={1} align="stretch">
        <NavItem to="/" icon={FiGrid}>Dashboard</NavItem>
        <NavItem to="/devices" icon={FiServer}>Devices</NavItem>
        <NavItem to="/discoveries" icon={FiSearch}>Discoveries</NavItem>
        <NavItem to="/path-visualizer" icon={FiMap}>Path Visualizer</NavItem>
        <NavItem to="/settings" icon={FiSettings}>Settings</NavItem>
      </VStack>
    </Box>
  );
};

export default Sidebar;
