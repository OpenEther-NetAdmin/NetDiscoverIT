import React from 'react';
import {
  Drawer, DrawerOverlay, DrawerContent, DrawerCloseButton,
  DrawerHeader, DrawerBody, Flex, Text, Badge,
} from '@chakra-ui/react';
import ChangeDetail from './ChangeDetail';
import { STATUS_COLORS } from './changeUtils';

const ChangeDrawer = ({ changeId, isOpen, onClose, statusHint, changeNumberHint }) => {
  return (
    <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="lg">
      <DrawerOverlay />
      <DrawerContent>
        <DrawerCloseButton />
        <DrawerHeader>
          <Flex align="center" gap={2}>
            <Text>{changeNumberHint || 'Change Detail'}</Text>
            {statusHint && (
              <Badge colorScheme={STATUS_COLORS[statusHint] || 'gray'} variant="solid">
                {statusHint}
              </Badge>
            )}
          </Flex>
        </DrawerHeader>
        <DrawerBody p={0}>
          {isOpen && changeId && (
            <ChangeDetail id={changeId} isDrawer={true} />
          )}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
};

export default ChangeDrawer;
