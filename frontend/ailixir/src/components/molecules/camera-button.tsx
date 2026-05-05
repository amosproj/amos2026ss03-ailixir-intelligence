import React, { useState } from 'react';
import * as ImagePicker from 'expo-image-picker';
import { Alert } from 'react-native';
import { CButton, CButtonProps } from '@/components/atoms';

export interface Photo {
  uri: string;
  width?: number;
  height?: number;
  type?: string;
}

export type CameraButtonProps = Omit<CButtonProps, 'onPress' | 'disabled' | 'opacity'> & {
  onPhoto: (photo: Photo) => void;
  onCancel?: () => void;
};

export const CameraButton: React.FC<CameraButtonProps> = ({ onPhoto, onCancel }) => {
  const [isLoading, setIsLoading] = useState(false);

  const requestCameraPermission = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    return status === 'granted';
  };

  const handleTakePhoto = async () => {
    try {
      // const photos: Photo[] = [];

      // while (true) {
      setIsLoading(true);

      // Request camera permission
      const hasPermission = await requestCameraPermission();
      if (!hasPermission) {
        Alert.alert('Permission Denied', 'Camera permission is required to take photos.');
        return;
      }

      // Launch camera
      const result = await ImagePicker.launchCameraAsync({
        allowsEditing: false,
        aspect: [4, 3],
        quality: 1,
      });

      // Handle result
      if (!result.canceled) {
        const photo: Photo = {
          uri: result.assets[0].uri,
          width: result.assets[0].width,
          height: result.assets[0].height,
          type: result.assets[0].type ?? undefined,
        };
        // photos.push(photo);
        onPhoto(photo);
      } else if (onCancel) {
        onCancel();
      }
      // else {
      //   break;
      // }
      // }

      // onPhotos(photos);
    } catch (error) {
      console.error('Error taking photo:', error);
      Alert.alert('Error', 'Failed to take photo. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <CButton onPress={handleTakePhoto} disabled={isLoading} opacity={isLoading ? 0.6 : 1}>
      {isLoading ? 'Taking Photo...' : 'Take Photo'}
    </CButton>
  );
};
