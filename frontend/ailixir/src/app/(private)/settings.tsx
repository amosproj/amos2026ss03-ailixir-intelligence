import { CButton } from '@/components/atoms';
import React from 'react';
import { getAuth, signOut } from '@firebase/auth';

export default function SettingsScreen() {
  const auth = getAuth();
  //const user = auth.currentUser; //for displaying the name, etc
  return (
    <>
      <CButton bg="lightcoral" onPress={() => signOut(auth)}>
        Log Out
      </CButton>
    </>
  );
}
