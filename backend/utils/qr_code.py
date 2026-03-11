import os
import io
import qrcode
from qrcode.image.styledpil import StyledPilImage
import base64


def generate_member_qr(member_id, gym_id):
    """Generate a QR code for a member's check-in.

    Returns a base64-encoded PNG image string.
    """
    data = f"GYMDESK:CHECKIN:{member_id}:{gym_id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1a1a2e", back_color="#ffffff")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return f"data:image/png;base64,{img_base64}"


def parse_qr_data(qr_string):
    """Parse QR code data back to member_id and gym_id."""
    try:
        parts = qr_string.split(':')
        if len(parts) == 4 and parts[0] == 'GYMDESK' and parts[1] == 'CHECKIN':
            return {
                'member_id': int(parts[2]),
                'gym_id': int(parts[3])
            }
    except (ValueError, IndexError):
        pass
    return None
