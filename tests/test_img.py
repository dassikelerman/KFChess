from unittest.mock import patch

import numpy as np

from view.img import Img


def make_img():
    img = Img()
    img.img = np.zeros((2, 2, 3), dtype="uint8")
    return img


def test_show_calls_cv2_imshow_with_the_given_window_name():
    img = make_img()
    with patch("cv2.imshow") as mock_imshow:
        img.show("MyWindow")
    mock_imshow.assert_called_once_with("MyWindow", img.img)


def test_show_defaults_to_a_window_name_when_none_is_given():
    img = make_img()
    with patch("cv2.imshow") as mock_imshow:
        img.show()
    mock_imshow.assert_called_once_with("Image", img.img)


def test_show_does_not_call_waitkey_or_destroy_all_windows():
    img = make_img()
    with patch("cv2.imshow"), patch("cv2.waitKey") as mock_wait, patch("cv2.destroyAllWindows") as mock_destroy:
        img.show()
    mock_wait.assert_not_called()
    mock_destroy.assert_not_called()
