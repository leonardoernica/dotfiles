import getpass,unittest
from unittest.mock import patch
import wifi_backend as w
from gi.repository import NM
class BackendTests(unittest.TestCase):
 def test_escape(self):
  self.assertEqual(w.fields(r'*:A\:B\\C__COLON__:80:WPA2:A4\:00:wlo1'),['*','A:B\\C__COLON__','80','WPA2','A4:00','wlo1'])
 def test_active_survives_stronger_duplicate(self):
  with patch.object(w,'command',side_effect=['enabled',':Home:90:WPA2:01\\:02:wlo1\n*:Home:30:WPA2:01\\:03:wlo1']):nets=w.scan()[1]
  self.assertEqual(len(nets),1);self.assertTrue(nets[0]['active']);self.assertEqual(nets[0]['bssid'],'01:03')
 def test_disabled(self):
  with patch.object(w,'command',return_value='disabled') as run:self.assertEqual(w.scan(),(False,[]));self.assertEqual(run.call_count,1)
 def test_personal_secret_over_dbus(self):
  net=dict(ssid='Test network',device='wlo1',bssid='02:00:00:00:00:01',security='WPA2')
  with patch.object(w,'_client'),patch.object(w,'profiles',return_value=[]),patch.object(w,'_call') as call,patch.object(w,'activate') as activate:
   w.connect(net,'a test password');c=NM.SimpleConnection.new_from_dbus(call.call_args.args[3].get_child_value(0))
   self.assertEqual(c.get_setting_connection().get_property('permissions'),[f'user:{getpass.getuser()}:'])
   self.assertEqual(c.get_setting_wireless_security().get_psk(),'a test password');self.assertEqual(call.call_args.args[2],'AddConnection2');self.assertNotIn('a test password',str(activate.call_args))
 def test_bad_password_does_not_write(self):
  with patch.object(w,'_call') as call:
   with self.assertRaises(w.WifiError):w.connect(dict(security='WPA2'),'short')
   call.assert_not_called()
 def test_enterprise(self):
  with self.assertRaises(w.WifiError):w.connect(dict(security='WPA2 802.1X'),'some-password')
 def test_errors(self):self.assertIn('DHCP',w.error_message(w.WifiError('IP configuration could not be reserved')))
 def test_disconnect_uses_device(self):
  with patch.object(w,'command') as cmd:w.disconnect(dict(ssid='different from profile',device='wlo1'));cmd.assert_called_once_with('device','disconnect','wlo1')
if __name__=='__main__':unittest.main()
