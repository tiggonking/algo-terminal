# QuantAlpha OMS - ChangeLog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unpublished

## 0.1.17.5
- various fixes to NAV monitor
- backup NAV Performance files in Archive folder

## 0.1.17.4
- fixed bug that would only report NAV for the first connected account.
- rebuilt NAV reporting to use pandas + export to excel.

## 0.1.17.3
## Added
- Full disconnect and reconnect of API when Account Updates not received
- Add archive button to reduce Trade Register file size

## 0.1.17
## Fixed
- change to AccountUpdates wait times to allow for larger # transactions


## 0.1.16.7 - 2024-11-06
## Changed
- only report ShortMargin check error if no data available from IB.  if an instrument
  is not found in the file, standard margins are assumed and no error reported.
- NAV file - only show withdrawals/deposits on withdrawal/deposit dates, not cumulative.

## 0.1.16.6 - 2024-09-13
## Changed
- allow additional exit order to placed if existing Partial Fill exit order

## 0.1.16.4 - 2024-08-20
## Added
- request current prices up to 10 times to ensure current prices always obtained
- add order size to order placement email report
- verbose logging on order files - source file name, order count, strategy list 
- Add prior day's performance data to Daily Report
- Add NAVs to Daily Report

## Changed
- added Could not obtain ShortMargin/FeeRate warnings to order email report
- remove Advisor account from Performance Report.


## 0.1.16
### Changed
- Migrate ad hoc emails into Email Manager
- Standardised Trade History export between Daily Report and Full Trade History files.
- Added Total PnL (columns and summary row) to Daily Report.
- .exe file name changed to 'QuantAlphaOMS'
### Deprecated
### Removed
### Fixed
- Emails correctly sent to multiple recipients
- Fixed bug where RT File and Daily Report manual buttons were resetting daily timers.
### Security

## 0.1.15 - 2024-05-07
### Changed
- Emails to multiple recipients are sent in separate actions
- Verify TWS connection prior to submitting orders

## 0.1.14 - 2024-06-21
### Changed
- Refactored email handling into separate module, to enable ad hoc email calls. 
- Trade Export button now exports a CSV file for each account (previously all accounts exported to a single Excel file)
- Trade Export file columns updated
### Fixed
- nav_monitor.py -  Corrected YTD and MTD profit calculations to reference NAV at the last day of previous year/month, 
  or, in the case where there is no previous year/month, the earliest available NAV is used in the calculation.
- Fixed bug that prevented the app from running in C:\Program Files\QA OMS folder
