Feature: Lối vào "Cuộc trò chuyện mới"
  Là người dùng, tôi luôn muốn có cách bắt đầu một cuộc chat mới —
  qua entry trong drawer và qua một nút nổi (FAB) trên các màn không phải Chat.

  Background:
    Given tôi đã đăng nhập và đang ở trong app chính (MainNavigator)

  Scenario: Entry "Cuộc trò chuyện mới" trong drawer
    When tôi mở drawer điều hướng
    Then tôi thấy một nút nổi bật "Cuộc trò chuyện mới" ở phần trên của drawer
    When tôi bấm nút "Cuộc trò chuyện mới"
    Then app điều hướng tới màn Chat với một cuộc trò chuyện mới trống (không có id)
    And drawer đóng lại

  Scenario: FAB hiển thị trên màn KHÔNG phải Chat (drawer screens)
    Given tôi đang ở màn "Dashboard", "Công việc" hoặc "Cài đặt"
    Then một Floating Action Button hiện cố định ở góc phải-dưới màn hình

  Scenario: FAB hiển thị trên các màn phụ (pushed screens)
    Given tôi đang ở một màn push như "Team", "Notes" hoặc "Conversations"
    Then một Floating Action Button hiện cố định ở góc phải-dưới màn hình

  Scenario: FAB bị ẩn trên màn Chat
    Given tôi đang ở màn Chat
    Then KHÔNG có Floating Action Button "Cuộc trò chuyện mới" nào hiển thị

  Scenario: Bấm FAB mở cuộc trò chuyện mới
    Given tôi đang ở một màn không phải Chat và thấy FAB
    When tôi bấm FAB
    Then app điều hướng tới màn Chat với một cuộc trò chuyện mới trống (không có id)

  Scenario: FAB tôn trọng safe-area
    Given thiết bị có home-indicator / notch
    Then FAB không bị che và cách mép dưới/phải một khoảng an toàn theo insets
