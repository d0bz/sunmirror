# Sector mapping for the mirror array
# Each sector represents a group of mirrors that work together

# Right side sectors (1-3)
SECTOR_1 = [0,6,7,8,24,25,26,27,28]       # Top right sector
SECTOR_2 = [1,9,10,11,29,30,31,32,33]     # Middle right sector
SECTOR_3 = [2,12,13,14,34,35,36,37,38]    # Bottom right sector


# Left side sectors (4-6)
SECTOR_4 = [3,15,16,17,39,40,41,42,43]  # Bottom left sector
SECTOR_5 = [4,18,19,20,44,45,46,47,48]     # Middle left sector
SECTOR_6 = [5,21,22,23,49,50,51,52,53]  # Top left sector

# Side groupings
RIGHT_SIDE = SECTOR_1 + SECTOR_2 + SECTOR_3
LEFT_SIDE = SECTOR_4 + SECTOR_5 + SECTOR_6

# Dictionary for easy sector lookup
SECTORS = {
    1: SECTOR_1,
    2: SECTOR_2,
    3: SECTOR_3,
    4: SECTOR_4,
    5: SECTOR_5,
    6: SECTOR_6
}

def get_sector_for_channel(channel):
    """Returns the sector number (1-6) for a given channel."""
    for sector_num, channels in SECTORS.items():
        if channel in channels:
            return sector_num
    return None

def get_side_for_channel(channel):
    """Returns 'left' or 'right' for a given channel."""
    if channel in LEFT_SIDE:
        return 'left'
    elif channel in RIGHT_SIDE:
        return 'right'
    return None
