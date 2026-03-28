import React from 'react';
import { NavLink } from 'react-router-dom';
import { Box, VStack, Text, Icon, Flex, Select } from '@chakra-ui/react';
import { FiGrid, FiServer, FiSearch, FiMap, FiSettings, FiClipboard, FiShare2, FiCheckCircle, FiMessageCircle } from 'react-icons/fi';
import { useOrg } from '../context/OrgContext';

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
  // OrgContext owns MSP state — derived from getMspOverview() response, not user.role.
  // This means the switcher appears iff the backend confirms MSP access, regardless of
  // which MSP role the JWT carries (msp_admin or msp_viewer).
  const { activeOrg, managedOrgs, isMsp, switchOrg } = useOrg();

  const handleOrgChange = (e) => {
    switchOrg(e.target.value);
  };

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

      {isMsp && managedOrgs.length > 0 && (
        <Box px={4} mb={4}>
          <Text fontSize="9px" fontWeight="bold" color="gray.400" letterSpacing="wider" mb={1}>
            ORG
          </Text>
          <Select
            size="sm"
            value={activeOrg?.id || ''}
            onChange={handleOrgChange}
            data-testid="org-switcher"
          >
            {managedOrgs.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </Select>
        </Box>
      )}

      <VStack spacing={1} align="stretch">
        <NavItem to="/" icon={FiGrid}>Dashboard</NavItem>
        <NavItem to="/devices" icon={FiServer}>Devices</NavItem>
        <NavItem to="/discoveries" icon={FiSearch}>Discoveries</NavItem>
        <NavItem to="/changes" icon={FiClipboard}>Changes</NavItem>
        <NavItem to="/path-visualizer" icon={FiMap}>Path Visualizer</NavItem>
        <NavItem to="/topology" icon={FiShare2}>Topology</NavItem>
        <NavItem to="/compliance" icon={FiCheckCircle}>Compliance</NavItem>
        <NavItem to="/assistant" icon={FiMessageCircle}>Assistant</NavItem>
        <NavItem to="/settings" icon={FiSettings}>Settings</NavItem>
      </VStack>
    </Box>
  );
};

export default Sidebar;
