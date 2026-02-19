def cmp_func(A, B):
    # Extract for A and B (assume each is a dict with 'obj', 'base_obj', 'obj_im', and precomputed 'origin_screen_x', 'origin_screen_y', 'bbox')
    if A == B:
        return 0

    # Default key: grid depth (higher sum is closer/front)
    key_A = A["obj"]["x"] + A["obj"]["y"]
    key_B = B["obj"]["x"] + B["obj"]["y"]

    # Check if screen bboxes overlap (for potential occlusion)
    ax1, ay1, ax2, ay2 = A["bbox"]
    bx1, by1, bx2, by2 = B["bbox"]
    overlap = not (ax2 < bx1 or ax1 > bx2 or ay2 < by1 or ay1 > by2)

    if overlap:
        # If A has depthPoints (assume list of dicts with 'x', 'y'; at least 2 for line)
        A_depth_points = A["base_obj"].get("depthPoints", [])
        B_depth_points = B["base_obj"].get("depthPoints", [])

        # if len(A_depth_points) == 1:
        #     dp = A_depth_points[0]
        #     A['origin_screen_x'] = A['pos'][0] + dp['x']
        #     A['origin_screen_y'] = A['pos'][1] + dp['y']
        #
        # if len(B_depth_points) == 1:
        #     dp = B_depth_points[0]
        #     B['origin_screen_x'] = B['pos'][0] + dp['x']
        #     B['origin_screen_y'] = B['pos'][1] + dp['y']

        if len(A_depth_points) >= 2:
            dp = sorted(A_depth_points, key=lambda p: p["x"])
            # Assume first two points define the line (extend if more)
            dp1 = dp[0]
            dp2 = dp[1]
            # Line points in screen space (relative to A's origin)
            p1_x = A["origin_screen_x"] + dp1["x"]
            p1_y = A["origin_screen_y"] + dp1["y"]
            p2_x = A["origin_screen_x"] + dp2["x"]
            p2_y = A["origin_screen_y"] + dp2["y"]

            # Vector for line
            dx = p2_x - p1_x
            dy = p2_y - p1_y

            # Vector from p1 to B's origin
            qx = B["origin_screen_x"] - p1_x
            qy = B["origin_screen_y"] - p1_y

            # Cross product to determine side (positive = one side, negative = other)
            cross = (dx * qy) - (dy * qx)

            # Assumption: positive cross means B is in front of A (adjust sign based on testing/orientation; e.g., if your lines are oriented left-to-right and front is below)
            if cross > 0:
                return -1  # B in front -> draw A first (behind)
            elif cross < 0:
                return 1  # B behind -> draw A after (in front)

        # Symmetric check if B has depthPoints
        if len(B_depth_points) >= 2:
            # Same logic, but swapped (compute cross for A's origin relative to B's line)
            dp = sorted(B_depth_points, key=lambda p: p["x"])
            dp1 = dp[0]
            dp2 = dp[1]
            p1_x = B["origin_screen_x"] + dp1["x"]
            p1_y = B["origin_screen_y"] + dp1["y"]
            p2_x = B["origin_screen_x"] + dp2["x"]
            p2_y = B["origin_screen_y"] + dp2["y"]
            dx = p2_x - p1_x
            dy = p2_y - p1_y
            qx = A["origin_screen_x"] - p1_x
            qy = A["origin_screen_y"] - p1_y
            cross = (dx * qy) - (dy * qx)
            if cross > 0:
                return 1  # A in front of B -> A after B
            elif cross < 0:
                return -1  # A behind B -> A before B

    # Fallback to default key if no depth resolution or no overlap
    return (key_A > key_B) - (
        key_A < key_B
    )  # -1 if key_A < key_B (A behind), 1 if key_A > key_B (A front)
