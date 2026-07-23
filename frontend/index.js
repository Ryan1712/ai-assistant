import "react-native-gesture-handler"; // PHẢI là import đầu tiên (yêu cầu của thư viện)
import { registerRootComponent } from "expo";
import App from "./App";

// Entry point (đã bỏ expo-router). Đăng ký App làm root component.
registerRootComponent(App);
