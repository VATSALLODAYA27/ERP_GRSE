import type { Box } from '../api'

export interface Mark {
  bbox: Box
  number: number
  tone: string
}

/** A drawing sheet with numbered boxes on it. Positions are in PDF points and are scaled to the image. */
export default function SheetViewer({ src, alt, pageSize, marks }: { src: string; alt: string; pageSize: [number, number]; marks: Mark[] }) {
  const [pageWidth, pageHeight] = pageSize

  // Several marks can point at the same place (one part row can fail two rules): one box, all their numbers.
  const boxes = new Map<string, { bbox: Box; numbers: number[]; tone: string }>()
  for (const mark of marks) {
    const key = mark.bbox.join()
    const box = boxes.get(key) ?? { bbox: mark.bbox, numbers: [], tone: mark.tone }
    box.numbers.push(mark.number)
    boxes.set(key, box)
  }

  return (
    <div className="sheet">
      <img src={src} alt={alt} />
      {[...boxes.values()].map(({ bbox: [x0, y0, x1, y1], numbers, tone }, i) => (
        <div
          key={numbers.join()}
          // Number badges alternate between the left and right end, so boxes on neighbouring rows do not hide each other's number.
          className={i % 2 ? 'sheet-marker badge-right' : 'sheet-marker'}
          style={{
            left: `${(x0 / pageWidth) * 100}%`,
            top: `${(y0 / pageHeight) * 100}%`,
            width: `${((x1 - x0) / pageWidth) * 100}%`,
            height: `${((y1 - y0) / pageHeight) * 100}%`,
            borderColor: tone,
          }}
        >
          <span style={{ background: tone }}>{numbers.join(', ')}</span>
        </div>
      ))}
    </div>
  )
}
