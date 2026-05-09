import { useWindowDimensions } from 'react-native';

export function useTablet(): boolean {
  const { width } = useWindowDimensions();
  return width >= 768;
}
