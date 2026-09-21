"""Putting marks on the page: geometry, fonts, strokes and pictures.

`geometry` is the only place that knows the digitizer is rotated; everything
above it is screen space. `hershey` and `skeleton` are the two ways to turn
text into pen paths and are interchangeable above `style`. `draw`, `diagram`,
`page`, `image` and `lineart` are shapes rather than letters.
"""
