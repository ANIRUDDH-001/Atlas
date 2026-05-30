# Decision 1: Detection Model and Tracker Configuration

Modified BoT-SORT defaults: increased track_buffer from 30 to 45 frames
(3 seconds at 15fps) to handle partial occlusion behind retail displays.
Enabled with_reid=True because retail density causes frequent crossing
paths. Increased proximity_thresh to 0.6 to account for face blur
reducing appearance embedding quality.
