# uv rig calibration targets

print all three at 100% (no "fit to page"), A4 landscape, and check the 100 mm bar with a ruler.
ordinary laser/inkjet on plain paper is fine: toner is uv-dark, paper is uv-mid-grey; the
s-bahn map registered at 20 cm this way. avoid glossy paper (specular glare from the sun/lamp).

- charuco_near_32mm.pdf   8x6 squares, 32 mm, marker ids 0-23, for 20-60 cm
- charuco_far_55mm.pdf    5x3 squares, 55 mm, marker ids 24-30, for 60-150 cm
- fiducials_200x120.pdf   four bullseyes on a 200x120 mm rectangle + centre cross, for manual
                          correspondences and for when the scope sees only a corner

## shooting protocol (per mounting orientation of the camera plug)

the mapping scope->phone for a plane is a homography that depends on distance Z. the plug is
reversible and the camera's angle relative to the phone flips with it, so calibrate each way
the plug can go in, and note which way it was.

1. phone orientation as you will shoot (landscape for the terrace rig). set rotate/mirror in
   the app once, they get baked into recordings.
2. tape the board flat to a wall or lay it on the floor. keep the board fronto-parallel to the
   phone for the first series; a tilted series is a bonus.
3. take a paired SNAPSHOT (not video) with the board filling most of the scope frame at
   measured distances: 20, 30, 40, 60 cm with the near board; 60, 80, 100, 150 cm with the far
   board. measure lens-to-board with a tape, write the distance on a sticky note in the phone
   frame's corner if you like.
4. one extra pair at each distance with the board rotated 90 deg on the wall catches any
   anisotropy in the scope's pixel aspect.
5. keep both files of each pair together; the app names them SCOPE_<t>.jpg / _vis.jpg.

what comes out: per pair, charuco corners in both images give an exact homography; across the
series the corner offsets fit the model  offset = f * (B/Z - tan theta)  which yields the
baseline B, the toe-in theta and the scope's focal length, after which any later shot needs only
one known-depth correspondence (or the bird's own features) to be registered.
