import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QListWidget, QListWidgetItem, QLabel, QGraphicsScene, QGraphicsView, QGraphicsPixmapItem, QGridLayout, QScrollArea
import os
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QSize, QPointF
from PyQt6.QtGui import QPixmap, QIcon, QCursor, QPainter, QTransform
from math import atan2, degrees

class Command:
    def undo(self):
        pass

class CustomGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.imageEditor = parent
        self.setMouseTracking(True)  # Start tracking mouse movement

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.imageEditor.beginStampRotation(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.imageEditor.currentlyRotatingItem:
            self.imageEditor.rotateStamp(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.imageEditor.endStampRotation(event)

    def keyPressEvent(self, event):
        # Call the handleKeyPress method of the ImageEditor instance
        self.imageEditor.handleKeyPress(event)

class AddStampCommand(Command):
    def __init__(self, scene, item):
        self.scene = scene
        self.item = item

    def undo(self):
        self.scene.removeItem(self.item)

class ClickableLabel(QLabel):
    # Define a custom signal that sends a string (image path)
    stampSelected = pyqtSignal(str)

    def __init__(self, imagePath, parent=None):
        super().__init__(parent)
        self.imagePath = imagePath
        pixmap = QPixmap(imagePath)
        
        # Scale the image to a fixed size
        scaledPixmap = pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaledPixmap)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        # Emit the custom signal with the image path
        self.stampSelected.emit(self.imagePath)

class StampsGridWidget(QWidget):
    def __init__(self, imageEditor, parent=None):
        super().__init__(parent)
        self.imageEditor = imageEditor  # Store a reference to the ImageEditor instance
        self.layout = QGridLayout(self)
        self.setLayout(self.layout)
        self.stamps = []

    def addStamp(self, imagePath):
        stampLabel = ClickableLabel(imagePath, self)
        stampLabel.stampSelected.connect(self.imageEditor.setSelectedStamp)
        self.stamps.append(stampLabel)
        # Calculate the position in the grid layout
        position = len(self.stamps) - 1
        row = position // 4
        col = position % 4
        self.layout.addWidget(stampLabel, row, col)
        # Resize the stamp initially
        self.resizeStamp(stampLabel)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for stamp in self.stamps:
            self.resizeStamp(stamp)

    def resizeStamp(self, stampLabel):
        # Calculate the new size for the stamp
        new_stamp_width = self.width() // 4
        new_stamp_height = new_stamp_width
        pixmap = QPixmap(stampLabel.imagePath)
        scaledPixmap = pixmap.scaled(new_stamp_width, new_stamp_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        stampLabel.setPixmap(scaledPixmap)

    def setSelectedStamp(self, imagePath):
        self.parent().setSelectedStamp(imagePath)

class ImageEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cursorSize = QSize(32, 32)  # Set a fixed cursor size
        self.stampScaleFactor = 1.0
        self.isStampFlipped = False
        self.imagePaths = []  # Store paths of loaded images
        self.currentImageIndex = -1  # Current image index
        self.undoStack = []
        self.currentlyRotatingItem = None
        self.initialMousePos = None
        self.setWindowTitle('Image Stamp Editor')
        self.setGeometry(100, 100, 800, 600)
        self.initUI()
        self.imagePreview.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Add focus policy
        self.imagePreview.setMouseTracking(True)
        self.imagePreview.setFocus()  # Set focus
        self.editedScenes = {}

    def initUI(self):
        # Main layout
        mainLayout = QHBoxLayout()

        # Replace QLabel with QGraphicsView for image preview
        self.imagePreview = CustomGraphicsView(self)
        self.imagePreview.setStyleSheet("background-color: white; border: 1px solid black;")
        
        # Add image preview to main layout
        mainLayout.addWidget(self.imagePreview, 3)  # Larger weight for image preview

        # Replace self.stampsMenu with an instance of StampsGridWidget
        self.stampsMenu = StampsGridWidget(self)
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.stampsMenu)
        mainLayout.addWidget(scrollArea, 1)   # Add scroll area to the main layout

        self.loadStamps()

        # Add buttons
        loadImagesButton = QPushButton("Load Images")
        loadImagesButton.clicked.connect(self.loadImages)
        saveButton = QPushButton("Save Edits")
        saveButton.clicked.connect(self.saveEdits)

        # Create buttons for navigating images
        prevImageButton = QPushButton("Previous Image")
        prevImageButton.clicked.connect(self.previousImage)
        nextImageButton = QPushButton("Next Image")
        nextImageButton.clicked.connect(self.nextImage)

        # Bottom row for buttons
        bottomRow = QHBoxLayout()
        bottomRow.addWidget(loadImagesButton)
        bottomRow.addWidget(saveButton)
        bottomRow.addWidget(prevImageButton)
        bottomRow.addWidget(nextImageButton)

        # Overall layout
        overallLayout = QVBoxLayout()
        overallLayout.addLayout(mainLayout, 4)     # Larger weight for main area
        overallLayout.addLayout(bottomRow, 1)      # Smaller weight for bottom row

        centralWidget = QWidget()
        centralWidget.setLayout(overallLayout)
        self.setCentralWidget(centralWidget)

        # Set up mouse click event for imagePreview
        self.imagePreview.setMouseTracking(True)
        self.imagePreview.mousePressEvent = self.placeStampOnImage

        self.imagePreview.wheelEvent = self.scaleStamp


    def loadImages(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.currentImageFolder = folder  # Keep track of the current image folder
            self.imagePaths = [os.path.join(folder, f) for f in os.listdir(folder)
                               if f.endswith(('.png', '.jpg', '.jpeg'))]
            self.currentImageIndex = 0  # Start with the first image
            self.displayImageAtIndex()

    def displayImageAtIndex(self):
        if 0 <= self.currentImageIndex < len(self.imagePaths):
            imagePath = self.imagePaths[self.currentImageIndex]
            pixmap = QPixmap(imagePath)

            # Check if we already have an edited scene for this image
            if imagePath in self.editedScenes:
                # Use the existing edited scene
                self.scene = self.editedScenes[imagePath]
            else:
                # Create a new scene and add the image as the first item
                self.scene = QGraphicsScene(self)
                self.scene.addItem(QGraphicsPixmapItem(pixmap))
                self.editedScenes[imagePath] = self.scene  # Store the scene

            # Display the scene in the QGraphicsView
            self.imagePreview.setScene(self.scene)
            self.imagePreview.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def nextImage(self):
        if self.currentImageIndex < len(self.imagePaths) - 1:
            self.currentImageIndex += 1
            self.displayImageAtIndex()

    def previousImage(self):
        if self.currentImageIndex > 0:
            self.currentImageIndex -= 1
            self.displayImageAtIndex()

    def handleKeyPress(self, event):
        # Handle the key press event
        if event.key() == Qt.Key.Key_Right:
            self.nextImage()
        elif event.key() == Qt.Key.Key_Left:
            self.previousImage()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undoAction()

    def undoAction(self):
        if self.undoStack:
            command = self.undoStack.pop()
            command.undo()

    def displayImage(self, pixmap):
        # Clear the existing scene
        if hasattr(self, 'scene'):
            self.scene.clear()

        # Create a new scene with the image
        self.scene = QGraphicsScene(self)
        self.imagePreview.setScene(self.scene)
        item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(item)

        # Fit the image in the view
        self.imagePreview.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


    def saveEdits(self):
        if hasattr(self, 'currentImageFolder') and hasattr(self, 'scene'):
            # Create a sub-folder named 'edited'
            editedFolderPath = os.path.join(self.currentImageFolder, 'edited')
            if not os.path.exists(editedFolderPath):
                os.makedirs(editedFolderPath)

            # Iterate through the edited images and save them
            # Here, we'll just save the currently displayed image as an example
            for item in self.scene.items():
                if isinstance(item, QGraphicsPixmapItem):
                    pixmap = item.pixmap()
                    # Create a filename for the saved image
                    editedFilename = os.path.join(editedFolderPath, 'edited_image.png')
                    pixmap.save(editedFilename)
                    break  # Remove this break to handle multiple images
            print(f"Saved edited image to {editedFilename}")

    def loadStamps(self):
        stampsPath = "./stamps"
        if os.path.exists(stampsPath):
            for filename in os.listdir(stampsPath):
                if filename.endswith(('.png', '.jpg', '.jpeg')):
                    imagePath = os.path.join(stampsPath, filename)
                    self.stampsMenu.addStamp(imagePath)  # Use the addStamp method

    def setSelectedStamp(self, imagePath):
        self.selectedStampPath = imagePath
        self.updateCursorWithStamp(imagePath)

    def updateCursorWithStamp(self, imagePath):
        if imagePath:
            # Load the stamp image
            pixmap = QPixmap(imagePath)
            # Apply flipping if needed
            if self.isStampFlipped:
                pixmap = pixmap.transformed(QTransform().scale(-1, 1))
            # Scale the pixmap to the cursor size with the current scale factor
            cursorPixmap = pixmap.scaled(self.cursorSize * self.stampScaleFactor, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            # Set the cursor for the imagePreview
            self.imagePreview.setCursor(QCursor(cursorPixmap))

    def placeStampOnImage(self, event):
        if self.selectedStampPath and not self.currentlyRotatingItem:
            scenePosition = self.imagePreview.mapToScene(event.position().toPoint())
            pixmap = QPixmap(self.selectedStampPath)
            currentZoom = self.imagePreview.transform().m11()
            adjustedSize = self.cursorSize * self.stampScaleFactor / currentZoom
            scaledPixmap = pixmap.scaled(adjustedSize, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if self.isStampFlipped:
                scaledPixmap = scaledPixmap.transformed(QTransform().scale(-1, 1))
            item = QGraphicsPixmapItem(scaledPixmap)
            stampPosition = QPointF(scenePosition.x() - adjustedSize.width() / 2, scenePosition.y() - adjustedSize.height() / 2)
            item.setPos(stampPosition)
            self.scene.addItem(item)
            self.undoStack.append(AddStampCommand(self.scene, item))
            self.currentlyRotatingItem = item  # Set the item for potential rotation
            self.initialMousePos = event.pos()  # Store the initial position
            self.imagePreview.setMouseTracking(True)  # Start tracking mouse movement


    def cloneCurrentScene(self):
        # This method will clone the current scene and its items
        clonedScene = QGraphicsScene()
        for item in self.scene.items():
            # For simplicity, we're assuming all items are QGraphicsPixmapItem instances
            clonedItem = QGraphicsPixmapItem(item.pixmap())
            clonedItem.setPos(item.pos())
            clonedItem.setTransform(item.transform())
            clonedScene.addItem(clonedItem)
        return clonedScene

    def saveEdits(self):
        # Iterate over the edited scenes and save each one
        for imagePath, editedScene in self.editedScenes.items():
            # Determine the directory and filename for saving
            imageFolder = os.path.dirname(imagePath)
            editedFolderPath = os.path.join(imageFolder, 'edited')
            os.makedirs(editedFolderPath, exist_ok=True)  # Create 'edited' folder if it doesn't exist
            editedFilename = os.path.join(editedFolderPath, os.path.basename(imagePath))

            # Render the edited scene to a QPixmap
            pixmap = QPixmap(editedScene.sceneRect().size().toSize())
            pixmap.fill(Qt.GlobalColor.transparent)  # Fill the pixmap with transparency if desired
            painter = QPainter(pixmap)
            editedScene.render(painter, QRectF(pixmap.rect()), editedScene.sceneRect())
            painter.end()

            # Save the QPixmap to the same filename as the original image
            pixmap.save(editedFilename)

    def scaleStamp(self, event):
        # Update scale factor based on the wheel delta
        if event.angleDelta().y() > 0:
            self.stampScaleFactor *= 1.1  # Scale up by 10%
        else:
            self.stampScaleFactor *= 0.9  # Scale down by 10%

        # Update cursor with new scale
        self.updateCursorWithStamp(self.selectedStampPath)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self.isStampFlipped = not self.isStampFlipped
            self.updateCursorWithStamp(self.selectedStampPath)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self.isStampFlipped = not self.isStampFlipped
            self.updateCursorWithStamp(self.selectedStampPath)

    def beginStampRotation(self, event):
        if self.currentlyRotatingItem:
            self.initialMousePos = self.imagePreview.mapToScene(event.pos())

    def rotateStamp(self, event):
        if self.currentlyRotatingItem:
            currentPos = self.imagePreview.mapToScene(event.pos())
            angleDelta = self.calculateRotationAngle(self.initialMousePos, currentPos)
            center = self.currentlyRotatingItem.boundingRect().center()
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.rotate(angleDelta)
            transform.translate(-center.x(), -center.y())
            self.currentlyRotatingItem.setTransform(transform)
            self.initialMousePos = event.pos()

    def endStampRotation(self, event):
        self.currentlyRotatingItem = None  # Clear the rotating item


    def calculateRotationAngle(self, initialPos, currentPos):
        # Get the item's center in scene coordinates
        itemCenter = self.currentlyRotatingItem.mapToScene(self.currentlyRotatingItem.boundingRect().center())

        # Calculate the vectors from the item center to the initial and current positions
        initialVector = initialPos - itemCenter
        currentVector = currentPos - itemCenter

        # Calculate the angles using atan2
        initialAngle = atan2(initialVector.y(), initialVector.x())
        currentAngle = atan2(currentVector.y(), currentVector.x())

        # Calculate the change in angle
        angleDelta = degrees(currentAngle - initialAngle)

        # Normalize the angleDelta to prevent unnecessary full rotations
        while angleDelta > 180:
            angleDelta -= 360
        while angleDelta < -180:
            angleDelta += 360

        return angleDelta

# Main function outside of the ImageEditor class
def main():
    app = QApplication(sys.argv)
    mainWin = ImageEditor()
    mainWin.show()
    mainWin.imagePreview.setFocus()  # Set focus to the imagePreview
    sys.exit(app.exec())

if __name__ == '__main__':
    main()