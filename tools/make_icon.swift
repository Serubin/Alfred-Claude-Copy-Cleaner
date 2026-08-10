#!/usr/bin/env swift
// Renders src/icon.png — the workflow icon Alfred shows in the workflow list and
// beside the Universal Action. A dark rounded tile with the ⏺ message bullet that
// this workflow exists to strip, plus a sweep of fading dots suggesting the cleanup.
//
//   swift tools/make_icon.swift

import AppKit

let side: CGFloat = 512
let image = NSImage(size: NSSize(width: side, height: side))

image.lockFocus()
guard let ctx = NSGraphicsContext.current?.cgContext else {
    fatalError("no graphics context")
}

// Background: the terminal-ish charcoal Alfred workflows tend to sit well against.
let inset: CGFloat = 16
let rect = NSRect(x: inset, y: inset, width: side - inset * 2, height: side - inset * 2)
let tile = NSBezierPath(roundedRect: rect, xRadius: 112, yRadius: 112)
NSColor(calibratedRed: 0.13, green: 0.13, blue: 0.14, alpha: 1).setFill()
tile.fill()

// Nothing may bleed past the tile's rounded corners.
ctx.saveGState()
tile.addClip()

// The ⏺ bullet in Claude's orange, then trailing dots fading out: the artifacts
// being swept away. Sizes and gaps are laid out from a measured total so the group
// sits centred in the tile rather than drifting right.
let accent = NSColor(calibratedRed: 0.85, green: 0.47, blue: 0.34, alpha: 1)
let sizes: [CGFloat] = [132, 88, 56]
let gaps: [CGFloat] = [40, 32]
let groupWidth = sizes.reduce(0, +) + gaps.reduce(0, +)

var x = (side - groupWidth) / 2
var alpha: CGFloat = 1.0
for (index, size) in sizes.enumerated() {
    accent.withAlphaComponent(alpha).setFill()
    NSBezierPath(ovalIn: NSRect(x: x, y: side / 2 - size / 2, width: size, height: size)).fill()
    x += size + (index < gaps.count ? gaps[index] : 0)
    alpha *= 0.55
}

ctx.restoreGState()

image.unlockFocus()

guard
    let tiff = image.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: tiff),
    let png = bitmap.representation(using: .png, properties: [:])
else {
    fatalError("could not encode png")
}

let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
let out = root.appendingPathComponent("src/icon.png")
try png.write(to: out)
print("wrote src/icon.png (\(png.count) bytes)")
_ = ctx
