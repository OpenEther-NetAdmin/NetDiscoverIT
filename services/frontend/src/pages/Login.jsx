import React, { useState } from 'react';
import { useNavigate, useLocation, Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Card,
  CardBody,
  CardHeader,
  FormControl,
  FormLabel,
  Input,
  Button,
  Heading,
  Text,
  VStack,
  Alert,
  AlertIcon,
  Link,
} from '@chakra-ui/react';
import { useAuth } from '../context/AuthContext';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Center minH="100vh" bg="gray.50">
      <Card w="100%" maxW="md" boxShadow="lg">
        <CardHeader textAlign="center">
          <Heading size="lg">NetDiscoverIT</Heading>
          <Text mt={2} color="gray.600">
            Sign in to your account
          </Text>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit}>
            <VStack spacing={4}>
              {error && (
                <Alert status="error">
                  <AlertIcon />
                  {error}
                </Alert>
              )}
              <FormControl isRequired>
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Password</FormLabel>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                />
              </FormControl>
              <Button
                type="submit"
                colorScheme="blue"
                w="100%"
                isLoading={loading}
              >
                Sign In
              </Button>
              <Text>
                Don't have an account?{' '}
                <Link as={RouterLink} to="/register" color="blue.500">
                  Register
                </Link>
              </Text>
            </VStack>
          </form>
        </CardBody>
      </Card>
    </Center>
  );
};

export default Login;
