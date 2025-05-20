from ibapi.client import *
from ibapi.wrapper import *
import time
import threading


class TestApp(EClient, EWrapper):
  def __init__(self):
    EClient.__init__(self, self)
  
  def nextValidId(self, orderId):
    self.orderId = orderId
  
  def nextId(self):
    self.orderId += 1
    return self.orderId
  
  def currentTime(self, time):
    print(time)
  def error(self, reqId, errorCode, errorString, advancedOrderReject="", extra=""):
    print(f"reqId: {reqId}, errorCode: {errorCode}, errorString: {errorString}, orderReject: {advancedOrderReject}, extra: {extra}")
    
    
def test_app():
    app = TestApp()
    app.connect("host.docker.internal", 7497, 0)
    threading.Thread(target=app.run).start()
    time.sleep(1)
    
    list_of_ids = []
    for i in range(0,5):
      list_of_ids.append(app.nextId())
      print(list_of_ids)
    time.sleep(1)
    app.disconnect()
    
    assert list_of_ids == [2,3,4,5,6]
    
if __name__ == "__main__":
  test_app()