# AlgoTerminal

## System Overview
AlgoTerminal is a sophisticated Order Management System (OMS) designed for algorithmic trading. The system provides:

- Automated order management and execution
- Multi-account support with Interactive Brokers integration
- Real-time market data monitoring
- Daily performance reporting and trade history tracking
- Configurable order processing (scheduled or manual)
- Comprehensive error handling and logging
- Email notifications for important events

The system maintains order file monitoring, initiates and maintains broker connections, places daily exit/entry orders, and generates daily report emails and RealTest output files.

## Dev Setup
[To be completed]

## Staging Setup
The staging environment is hosted on Azure VM. To access the staging environment:

1. Each developer must be whitelisted for access
2. The staging environment is used to test the executable before production deployment
3. Access is restricted to authorized personnel only
4. To connect to the VM you need to use RDP (available on Windows and Mac)
5. VM name: strategybuilder
6. You will be prompted for a pincode and the vm password. Mitch will provide these to you. 

The VM is setup with Norgate, RealTest, IB gateway, and the latest executable of the OMS.

## Production
[To be completed]

## Testing Process
[To be completed]