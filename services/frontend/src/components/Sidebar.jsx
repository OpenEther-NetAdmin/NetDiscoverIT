import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Box, VStack, Text, Icon, Flex, Select, Spinner } from '@chakra-ui/react';
import { FiGrid, FiServer, FiSearch, FiMap, FiSettings, FiClipboard } from 'react-icons/fi';
import { useAuth } from '../context/AuthContext';
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
  const { user } = useAuth();
  const { activeOrg, managedOrgs, isMsp: isMspOrg, switchOrg } = useOrg();
  const [loading, setLoading] = useState(true);
  const isMsp = user?.role === 'msp_admin' || user?.role === 'msp_engineer';

  useEffect(() => {
    if (isMspOrg) {
      setLoading(false);
    }
  }, [isMspOrg]);

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

      {isMsp && (
        <Box px={4} mb={4}>
          {loading ? (
            <Spinner size="sm" />
          ) : (
            <Select
              size="sm"
              value={activeOrg?.id || ''}
              onChange={handleOrgChange}
              placeholder="Select org"
              data-testid="org-switcher"
            >
              {managedOrgs.map(org => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </Select>
          )}
        </Box>
      )}

      <VStack spacing={1} align="stretch">
        <NavItem to="/" icon={FiGrid}>Dashboard</NavItem>
        <NavItem to="/devices" icon={FiServer}>Devices</NavItem>
        <NavItem to="/discoveries" icon={FiSearch}>Discoveries</NavItem>
        <NavItem to="/changes" icon={FiClipboard}>Changes</NavItem>
        <NavItem to="/path-visualizer" icon={FiMap}>Path Visualizer</NavItem>
        <NavItem to="/settings" icon={FiSettings}>Settings</NavItem>
      </VStack>
    </Box>
  );
};

export default Sidebar;
