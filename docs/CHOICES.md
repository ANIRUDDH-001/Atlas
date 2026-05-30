# Decision 1: Detection Model and Tracker Configuration

Modified BoT-SORT defaults: increased track_buffer from 30 to 45 frames
(3 seconds at 15fps) to handle partial occlusion behind retail displays.
Enabled with_reid=True because retail density causes frequent crossing
paths. Increased proximity_thresh to 0.6 to account for face blur
reducing appearance embedding quality.

Chose OSNet x0.25 (MSMT17) for Re-ID. AI suggested larger OSNet x1.0
for better accuracy. Overrode to x0.25 because: (1) faces are blurred —
larger models don't recover meaningful face features; (2) x0.25 runs at
~50ms/crop on CPU vs ~180ms for x1.0; (3) MSMT17 pretraining covers
indoor pedestrian scenarios similar to retail environments.

Staff detection via HSV upper-body colour histogram. AI suggested training
a binary classifier. Overrode because no labelled staff/customer training
data was available in the dataset. HSV hue is lighting-invariant — the
problem spec notes 'natural light, fluorescent, mixed' conditions, making
HSV more robust than RGB thresholds. Conservative threshold (0.25) means
we prefer calling a staff member a customer rather than excluding real
customers — false positives hurt conversion_rate accuracy.
