import { CButton } from '@/components/atoms';
import React, { useState, useEffect } from 'react';
import { getAuth, signOut } from '@firebase/auth';

export default function SettingsScreen() {
  const auth = getAuth();
  const user = auth.currentUser; //for displaying the name, etc
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const fetchToken = async () => {
      if (user) {
        try {
          const idToken = await user.getIdToken();
          setToken(idToken);
          console.log('Token:', token);
        } catch (error) {
          console.error('Error accessing the Token:', error);
        }
      }
    };

    fetchToken();
  }, [user, token]); // Triggert neu, wenn sich der User-Status ändert
  return (
    <>
      <CButton emphasis="high" fullWidth onPress={() => signOut(auth)}>
        Log Out
      </CButton>
    </>
  );
}
