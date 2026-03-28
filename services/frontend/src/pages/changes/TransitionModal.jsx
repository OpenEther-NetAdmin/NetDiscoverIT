import React, { useState } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter,
  Button, Textarea, Text,
} from '@chakra-ui/react';

const ACTION_CONFIG = {
  propose:   { label: 'Propose Change',      color: 'blue',   needsText: false, placeholder: '' },
  approve:   { label: 'Approve Change',      color: 'green',  needsText: true,  placeholder: 'Approval notes (optional)' },
  implement: { label: 'Mark as Implemented', color: 'purple', needsText: true,  placeholder: 'Implementation evidence' },
  verify:    { label: 'Verify Change',       color: 'teal',   needsText: true,  placeholder: 'Verification results' },
  rollback:  { label: 'Rollback Change',     color: 'red',    needsText: true,  placeholder: 'Reason for rollback' },
};

const TransitionModal = ({ isOpen, onClose, onConfirm, action, changeNumber, isLoading }) => {
  const [text, setText] = useState('');
  const config = ACTION_CONFIG[action] || { label: action, color: 'gray', needsText: false };

  const handleConfirm = () => {
    onConfirm(text);
    setText('');
  };

  const handleClose = () => {
    setText('');
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} isCentered>
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>{config.label}</ModalHeader>
        <ModalBody>
          <Text mb={3} color="gray.600">
            {changeNumber}
          </Text>
          {config.needsText && (
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={config.placeholder}
              rows={4}
            />
          )}
        </ModalBody>
        <ModalFooter gap={2}>
          <Button variant="ghost" onClick={handleClose}>Cancel</Button>
          <Button
            colorScheme={config.color}
            onClick={handleConfirm}
            isLoading={isLoading}
          >
            {config.label}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default TransitionModal;
