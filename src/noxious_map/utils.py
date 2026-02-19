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

        if len(A_depth_points) >= 2:
            dp_sorted = sorted(A_depth_points, key=lambda p: p["x"])
            # Use leftmost and rightmost for the line (better for >2 points)
            dp1 = dp_sorted[0]
            dp2 = dp_sorted[-1]
            # Line points in screen space (relative to A's origin)
            p1_x = A["origin_screen_x"] + dp1["x"]
            p1_y = A["origin_screen_y"] + dp1["y"]
            p2_x = A["origin_screen_x"] + dp2["x"]
            p2_y = A["origin_screen_y"] + dp2["y"]

            # Vector for line
            dx = p2_x - p1_x
            dy = p2_y - p1_y

            # Effective point for B (average of its depthPoints if present, else origin)
            b_eff_x = B["origin_screen_x"]
            b_eff_y = B["origin_screen_y"]
            if len(B_depth_points) > 0:
                avg_x = sum(p["x"] for p in B_depth_points) / len(B_depth_points)
                avg_y = sum(p["y"] for p in B_depth_points) / len(B_depth_points)
                b_eff_x += avg_x
                b_eff_y += avg_y

            # Vector from p1 to B's effective point
            qx = b_eff_x - p1_x
            qy = b_eff_y - p1_y

            # Cross product to determine side (positive = one side, negative = other)
            cross = (dx * qy) - (dy * qx)

            # Assumption: positive cross means B is in front of A (adjust sign based on testing/orientation; e.g., if your lines are oriented left-to-right and front is below)
            if cross > 0:
                return -1  # B in front -> draw A first (behind)
            elif cross < 0:
                return 1  # B behind -> draw A after (in front)

        # Symmetric check if B has depthPoints
        if len(B_depth_points) >= 2:
            # Same logic, but swapped (compute cross for A's effective point relative to B's line)
            dp_sorted = sorted(B_depth_points, key=lambda p: p["x"])
            dp1 = dp_sorted[0]
            dp2 = dp_sorted[-1]
            p1_x = B["origin_screen_x"] + dp1["x"]
            p1_y = B["origin_screen_y"] + dp1["y"]
            p2_x = B["origin_screen_x"] + dp2["x"]
            p2_y = B["origin_screen_y"] + dp2["y"]
            dx = p2_x - p1_x
            dy = p2_y - p1_y

            # Effective point for A
            a_eff_x = A["origin_screen_x"]
            a_eff_y = A["origin_screen_y"]
            if len(A_depth_points) > 0:
                avg_x = sum(p["x"] for p in A_depth_points) / len(A_depth_points)
                avg_y = sum(p["y"] for p in A_depth_points) / len(A_depth_points)
                a_eff_x += avg_x
                a_eff_y += avg_y

            # Vector from p1 to A's effective point
            qx = a_eff_x - p1_x
            qy = a_eff_y - p1_y

            cross = (dx * qy) - (dy * qx)
            if cross > 0:
                return 1  # A in front of B -> A after B
            elif cross < 0:
                return -1  # A behind B -> A before B

    # Fallback to default key if no depth resolution or no overlap
    return (key_A > key_B) - (
        key_A < key_B
    )  # -1 if key_A < key_B (A behind), 1 if key_A > key_B (A front)
