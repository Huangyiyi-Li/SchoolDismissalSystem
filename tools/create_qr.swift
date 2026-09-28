import AppKit
import CoreImage
import Foundation

let message = FileHandle.standardInput.readDataToEndOfFile()
guard !message.isEmpty,
      let filter = CIFilter(name: "CIQRCodeGenerator") else {
    exit(1)
}
filter.setValue(message, forKey: "inputMessage")
filter.setValue("M", forKey: "inputCorrectionLevel")
guard let source = filter.outputImage else { exit(1) }
let image = source.transformed(by: CGAffineTransform(scaleX: 8, y: 8))
let context = CIContext()
guard let cgImage = context.createCGImage(image, from: image.extent),
      let png = NSBitmapImageRep(cgImage: cgImage).representation(using: .png, properties: [:]) else {
    exit(1)
}
FileHandle.standardOutput.write(png)
