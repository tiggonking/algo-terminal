from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QBrush
from PyQt6.QtCore import Qt, QRect
import sys


class QASplashScreen(QSplashScreen):
    def __init__(self, pixmap, software_name, version_info, license_info="Proprietary Licence - Not for Distribution"):
        super().__init__(pixmap)
        self.software_name = software_name
        self.version_info = version_info
        self.license_info = license_info

    def drawContents(self, painter):
        # Create a gradient background
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#1E3C72"))
        gradient.setColorAt(1.0, QColor("#2A5298"))
        painter.fillRect(self.rect(), QBrush(gradient))

        # Draw software name with a bolder font and a lighter blue color
        painter.setPen(QColor("#F0F8FF"))  # AliceBlue color
        painter.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        name_rect = QRect(20, 20, self.width() - 40, 80)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.software_name)

        # Draw version information in a slightly smaller font
        painter.setFont(QFont("Arial", 14, QFont.Weight.Normal))
        version_text = f"Version: {self.version_info}"
        version_rect = QRect(20, 110, self.width() - 40, 30)
        painter.drawText(version_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, version_text)

        # Draw license information at the bottom with a grey color
        painter.setPen(QColor("#D3D3D3"))  # LightGrey color
        painter.setFont(QFont("Arial", 12, QFont.Weight.Normal))
        license_rect = QRect(20, self.height() - 40, self.width() - 40, 30)
        painter.drawText(license_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, self.license_info)


if __name__ == '__main__':

    app = QApplication(sys.argv)

    pixmap = QPixmap(500, 300)
    splash = QASplashScreen(
        pixmap=pixmap,
        software_name="Quantive Alpha\nOrder Management System",
        version_info='0.0.0',
        license_info="Proprietary Licence - Not for Distribution"
    )
    splash.show()

    app.processEvents()
    import time
    time.sleep(5)

    window = QWidget()
    window.show()
    splash.finish(window)

    sys.exit(app.exec())
