# UPE100

Python code samples from K-Cup vending machine


Files: UPE100.py, payment_manager.py

For context the machine utilizes a third party device called a UPE100 to perform credit card processing with payment providers. The UPE100 securely performs all the required data communication with the processor and provides the application that uses it an API to control it. The API itself consist of a set of HTML formatted commands and return status and event messages also formatted in HTML.  The application, in this case the K-Cup vending machine, communicates with the UPE100 by sending commands and getting responses using a TCP/IP socket. 
 
UPE100.py is a Python module to encapsulate the UPE100 API for use in the application. It defines a Python class named upe100 that handles all the low level details of interacting with the UPE100 device and provides the application a set of methods to simplify use of the UPE100 within the application code to actions like  “authorize a sale”, “cancel a sale” and so on. This module is UPE100 specific and not application specific so it can and has been used in other applications beyond the K-cup vending machine. 

Associated files:

-	DeviceFusion UPE100 Library.pptx – UPE100 Library Diagram
-	UPE100_API_Spec_v1.6.pdf – API specification from payment device manufacturer 
-	https://uicpayworld.com/products/semi-integrated/pot/ - payment device product specification
 
payment_manager.py  is an application level Python module from the K-Cup vending machine that handles the machine’s payment processing. It uses the above UPE100 object. The module consists of a Python thread class called PollCardReader that performs all payment related tasks for the vending machine. There are two main types of readers that are supported in the code, a traditional magnetic stripe reader and a chip card reader. The mag card reader support is more historical and the use of readers of this type are more or less obsolete. Currently chip card readers are used on the machine and the interface to the chip card is via the UPE100 device. There is also a software only based ‘emulation’ reader that is supported mainly for development purposes. Support for these different types of readers is via the definition of three additional Python classes that are also defined in payment_manager.py. The three reader classes are called MagStripe_Reader, UPE100_Reader, and Emulation_Reader. Each of the three reader classes are derived from a common base class called Generic_Reader. The use of these classes enables the PollCardReader and in turn the machine to easily support any type of card reader, even new types that may come into future use, with minimal code modification. 
